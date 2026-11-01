"""Calendar-aligned empirical historical-year rainfall bootstrap.
Historical rainfall observations are never fitted to construction delay labels.
"""
from pathlib import Path
from datetime import date, timedelta
import numpy as np
import pandas as pd

DEFAULT_FILE = Path(__file__).parent / 'data' / 'Mumbai_IMD_Rainfall_2015_2025_19N_72.75E.csv'

def load_and_validate(source=DEFAULT_FILE):
    raw = pd.read_csv(source)
    if list(raw.columns) != ['date', 'rainfall_mm']:
        raise ValueError('Expected exact columns date,rainfall_mm')
    dt = pd.to_datetime(raw.date, errors='coerce', format='%Y-%m-%d')
    rain = pd.to_numeric(raw.rainfall_mm, errors='coerce')
    if dt.isna().any() or rain.isna().any() or not np.isfinite(rain).all():
        raise ValueError('Missing/invalid dates or rainfall; dataset rejected')
    if (rain < 0).any() or dt.duplicated().any():
        raise ValueError('Negative rainfall or duplicate dates; dataset rejected')
    df = pd.DataFrame({'date': dt, 'rainfall_mm': rain}).sort_values('date').reset_index(drop=True)
    expected = pd.date_range(df.date.min(), df.date.max(), freq='D')
    if len(expected) != len(df) or not (df.date.to_numpy() == expected.to_numpy()).all():
        raise ValueError('Gaps in daily coverage; dataset rejected')
    sizes = df.groupby(df.date.dt.year).size()
    if any(v != (366 if pd.Timestamp(y,12,31).is_leap_year else 365) for y,v in sizes.items()):
        raise ValueError('Incomplete calendar year; dataset rejected')
    return df

def diagnostics(df, source_name=None):
    y = df.assign(year=df.date.dt.year, month=df.date.dt.month)
    expected = pd.date_range(df.date.min(), df.date.max(), freq='D')
    missing = int(len(expected) - len(df))
    return {'observations': len(df), 'start':str(df.date.min().date()),
            'end':str(df.date.max().date()), 'missing_observations': missing,
            'validation_status': 'PASS' if missing == 0 else 'FAIL',
            'source_name': source_name or 'Unspecified selected rainfall source',
            'zero_fraction':float((df.rainfall_mm==0).mean()),
            'maximum_mm':float(df.rainfall_mm.max()),
            'annual_mm':y.groupby('year').rainfall_mm.sum().round(2).to_dict(),
            'monthly_mean_total_mm':y.groupby(['year','month']).rainfall_mm.sum().groupby('month').mean().round(2).to_dict(),
            'monsoon_share':float(y[y.month.between(6,9)].rainfall_mm.sum()/y.rainfall_mm.sum()),
            'heavy_days_64_5mm':int((df.rainfall_mm>=64.5).sum())}

class HistoricalRainfall:
    def __init__(self, df):
        self.df=df
        self.years=sorted(df.date.dt.year.unique().tolist())
        # month-day index: leap-day on non-leap years uses 28 February (declared imputation for scenario alignment only).
        self.calendar={}
        self._rain_lookup=np.zeros((len(self.years),12,31),dtype=np.float64)
        self._year_to_index={y:i for i,y in enumerate(self.years)}
        for yi,y in enumerate(self.years):
            g=df[df.date.dt.year==y]
            self.calendar[y]={d.strftime('%m-%d'):float(r) for d,r in zip(g.date,g.rainfall_mm)}
            for d,r in zip(g.date,g.rainfall_mm):
                self._rain_lookup[yi,d.month-1,d.day-1]=float(r)
        # Non-leap historical years replay Feb 29 using Feb 28, as documented.
        for yi,y in enumerate(self.years):
            if not pd.Timestamp(y,12,31).is_leap_year:
                self._rain_lookup[yi,1,28]=self._rain_lookup[yi,1,27]

    def rainfall_for_dates(self, dates, year_index):
        """Vectorized continuous historical-year replay with year wraparound."""
        dates=np.asarray(dates,dtype='datetime64[D]')
        year_index=np.asarray(year_index,dtype=np.int64)
        years=dates.astype('datetime64[Y]').astype(np.int64)+1970
        months=dates.astype('datetime64[M]').astype(np.int64)%12
        month_start=dates.astype('datetime64[M]').astype('datetime64[D]')
        days=(dates-month_start).astype(np.int64)
        offsets=years-int(self.project_year)
        hist_idx=(year_index+offsets)%len(self.years)
        return self._rain_lookup[hist_idx,months,days]

def simulate_rainfall(acts, order, cfg, n=None, seed=None, multiplier=1.0,
                      threshold=64.5, historical=None, label='Historical bootstrap'):
    """Simulated historical-year resampling with rain-conditioned disruption.
    Assumed stop probability = min(1, rainfall_mm / threshold) * activity sensitivity.
    Sensitivity = min(1, delay_M / (duration * 0.35)).
    Simulated loss occurs only on rainy days; 1 lost calendar day moves the activity finish 1 day.
    Extra activity cost = loss * cM/max(dM,epsilon); plus one project-level day rate.
    """
    from engine import Result, cpm_baseline
    if historical is None:historical=HistoricalRainfall(load_and_validate())
    fractional = [a.id for a in acts if not float(a.dur).is_integer()]
    if fractional:
        raise ValueError('Production rainfall simulation requires whole calendar-day activity durations. Fractional durations found: ' + ', '.join(fractional))
    if any(a.dur <= 0 for a in acts):
        raise ValueError('Activity durations must be positive whole calendar days.')
    n=int(n if n is not None else cfg.n)
    if multiplier < 0:raise ValueError('Severity must be >=0')
    rng=np.random.default_rng(cfg.seed if seed is None else seed)
    yearindex=rng.integers(0,len(historical.years),size=n)
    historical.project_year=date.fromisoformat(cfg.start).year
    project_start=np.datetime64(cfg.start,'D')
    k=len(acts)
    starts=np.zeros((k,n),dtype=np.int32)
    finishes=np.zeros((k,n),dtype=np.float64)
    losses=np.zeros((k,n),dtype=np.float64)
    costs=np.zeros((k,n),dtype=np.float64)
    rain_tot=np.zeros((k,n),dtype=np.float64)
    for i in order:
        a=acts[i]
        begin=np.max(finishes[a.pi],axis=0) if a.pi else np.zeros(n)
        starts[i]=np.ceil(begin).astype(np.int32)
        # delay_M is a user-supplied sensitivity input, not fitted to IMD rainfall.
        sensitivity=min(1.0, a.dM / max(a.dur*0.35,1e-9))
        remaining=np.full(n,int(np.ceil(a.dur)),dtype=np.int32)
        current=starts[i].copy()
        lost=np.zeros(n)
        totalrain=np.zeros(n)
        # Stop-day Bernoulli draws: rain on each simulated calendar date, including delay spillover.
        cap=int(np.ceil(a.dur))+max(365,int(a.dP*10)+30)
        for t in range(cap):
            active=remaining>0
            if not active.any():break
            idx=np.flatnonzero(active)
            dates=project_start+current[idx].astype('timedelta64[D]')
            mm=historical.rainfall_for_dates(dates,yearindex[idx])
            totalrain[idx]+=mm
            p=np.clip((mm/max(threshold,1e-9))*sensitivity*multiplier,0,1)
            stopped=rng.random(len(idx))<p
            lost[idx]+=stopped
            remaining[idx]-=(~stopped).astype(np.int32)
            current[idx]+=1
        if (remaining>0).any():raise RuntimeError('Project could not progress under disruption assumptions')
        losses[i]=lost
        rain_tot[i]=totalrain
        costs[i]=lost*(a.cM/a.dM if a.dM>0 else 0.0)
        finishes[i]=current
    base=cpm_baseline(acts,order)
    delay=np.maximum(0,finishes.max(axis=0)-base)
    extra=costs.sum(axis=0)+delay*cfg.rate
    r=Result(acts,order,cfg,n,base,delay,extra,losses,costs,finishes,multiplier,multiplier,label)
    r.rain_exposure=rain_tot
    r.historical_years=np.asarray(historical.years)[yearindex]
    return r
