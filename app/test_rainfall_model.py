import numpy as np
import pandas as pd
import pytest
from datetime import date
import engine as E
import rainfall_model as R

def fixture():
    a=[E.Activity('A',dur=12,dM=5,dP=8,cM=2,cP=3),E.Activity('B',dur=8,pre=['A'],dM=3,dP=5,cM=1,cP=2)]
    c=E.Config(start='2027-07-01', n=1000,seed=42,rate=.5)
    err,_,order=E.validate(a,c)
    assert not err
    return a,order,c

def test_full_coverage():
    d=R.load_and_validate();assert len(d)==4018
    assert not d.date.duplicated().any()

def test_zero_rainfall_zero_delay(tmp_path):
    d=R.load_and_validate();d['rainfall_mm']=0
    a,o,c=fixture();r=R.simulate_rainfall(a,o,c,n=100,historical=R.HistoricalRainfall(d));assert np.all(r.delay==0) and np.all(r.extra==0)

def test_zero_sensitivity():
    a,o,c=fixture();r=R.simulate_rainfall(a,o,c,n=100,multiplier=0);assert np.all(r.delay==0)

def test_fixed_seed():
    a,o,c=fixture();r1=R.simulate_rainfall(a,o,c,n=100);r2=R.simulate_rainfall(a,o,c,n=100)
    assert np.array_equal(r1.delay,r2.delay) and np.array_equal(r1.extra,r2.extra)

def test_rainfall_effect():
    a,o,c=fixture();d=R.load_and_validate();dry=d.copy();dry['rainfall_mm']=0
    wet=d.copy();wet['rainfall_mm']=60
    r0=R.simulate_rainfall(a,o,c,n=100,historical=R.HistoricalRainfall(dry))
    r1=R.simulate_rainfall(a,o,c,n=100,historical=R.HistoricalRainfall(wet))
    assert r1.delay.mean()>r0.delay.mean()

def test_outside_vs_monsoon():
    a,o,c=fixture();c.start='2027-02-01';r0=R.simulate_rainfall(a,o,c,n=200)
    c.start='2027-07-01';r1=R.simulate_rainfall(a,o,c,n=200)
    assert r1.delay.mean()>r0.delay.mean()

def test_leap_year_and_year_transition():
    a,o,c=fixture()
    for start in ('2028-02-27','2027-12-29'):
        c.start=start
        r=R.simulate_rainfall(a,o,c,n=50)
        assert np.isfinite(r.delay).all()

def test_parallel_and_sequential_cpm():
    a=[E.Activity('A',dur=10),E.Activity('B',dur=6),E.Activity('C',dur=3,pre=['A','B'])]
    c=E.Config(n=1000,start='2027-01-01');_,_,o=E.validate(a,c)
    assert E.cpm_baseline(a,o)==13
    r=R.simulate_rainfall(a,o,c,n=50,multiplier=0);assert np.all(r.delay==0)

def test_cost_aggregation():
    a,o,c=fixture();r=R.simulate_rainfall(a,o,c,n=60)
    assert np.allclose(r.extra, r.act_cost.sum(axis=0)+c.rate*r.delay)

def test_percentile():
    assert E.percentile(np.array([0.,10.,20.,30.,40.]),.8)==32

def test_dataset_rejected_on_missing(tmp_path):
    d=R.load_and_validate().iloc[1:];p=tmp_path/'bad.csv';d.to_csv(p,index=False)
    with pytest.raises(ValueError):R.load_and_validate(p)

@pytest.mark.parametrize('duration', [1, 2, 7, 30, 365])
def test_zero_rainfall_zero_delay_for_every_permitted_duration(duration):
    d=R.load_and_validate(); d['rainfall_mm']=0.0
    a=[E.Activity('A',dur=duration,dM=duration*.2,dP=duration*.5,cM=1.0)]
    c=E.Config(start='2027-07-01',n=64,seed=9)
    result=R.simulate_rainfall(a,[0],c,historical=R.HistoricalRainfall(d))
    assert result.base == duration
    assert np.array_equal(result.delay,np.zeros(64))
    assert np.array_equal(result.finishes[0],np.full(64,duration))

def test_fractional_activity_duration_rejected():
    a=[E.Activity('A',dur=1.2,dM=.5)]
    c=E.Config(n=10)
    with pytest.raises(ValueError,match='whole calendar-day'):
        R.simulate_rainfall(a,[0],c)

def test_custom_rainfall_diagnostics_are_dataset_specific():
    bundled=R.load_and_validate()
    custom=bundled.copy(); custom['rainfall_mm']=custom['rainfall_mm']*2
    d=R.diagnostics(custom,'uploaded-test.csv')
    assert d['source_name']=='uploaded-test.csv'
    assert d['observations']==len(custom)
    assert d['annual_mm'][2015]==pytest.approx(float(custom[custom.date.dt.year==2015].rainfall_mm.sum()),abs=.01)
    assert d['validation_status']=='PASS' and d['missing_observations']==0

def test_june_september_only_dataset_rejected(tmp_path):
    d=R.load_and_validate()
    d=d[d.date.dt.month.between(6,9)]
    path=tmp_path/'monsoon_only.csv'; d.to_csv(path,index=False)
    with pytest.raises(ValueError): R.load_and_validate(path)

def test_legacy_controls_do_not_change_production_results():
    a,o,c=fixture()
    r1=R.simulate_rainfall(a,o,c,n=250,seed=123,multiplier=1.0)
    c.rho=.9; c.engine='precise'
    r2=R.simulate_rainfall(a,o,c,n=250,seed=123,multiplier=1.0)
    assert np.array_equal(r1.delay,r2.delay)
    assert np.array_equal(r1.extra,r2.extra)

def test_schedule_successors_shift_after_activity_disruption():
    d=R.load_and_validate(); d['rainfall_mm']=64.5
    a=[E.Activity('A',dur=2,dM=1,dP=2,cO=0,cM=1,cP=1), E.Activity('B',dur=2,pre=['A'],dM=1,dP=2,cO=0,cM=1,cP=1)]
    c=E.Config(start='2027-07-01',n=1000,seed=4)
    errors,_,order=E.validate(a,c); assert not errors
    r=R.simulate_rainfall(a,order,c,multiplier=0.5,historical=R.HistoricalRainfall(d))
    assert np.any(r.finishes[0] > 2)
    assert np.all(r.finishes[1] >= r.finishes[0] + 2)

def test_benchmark_outputs_reproducible():
    a,o,c=fixture()
    x=R.simulate_rainfall(a,o,c,n=500,seed=4242)
    y=R.simulate_rainfall(a,o,c,n=500,seed=4242)
    assert np.array_equal(x.delay,y.delay)
    assert np.array_equal(x.extra,y.extra)

def test_sample_project_benchmark_outputs_reproducible():
    from pathlib import Path
    rows=pd.read_csv(Path(__file__).parent/'sample_activities.csv').fillna('')
    acts=[E.Activity(id=str(r['id']),name=str(r['name']),dur=float(r['duration']),
        cost=float(r['cost']),pre=[x for x in str(r['predecessors']).split(';') if x],
        dO=float(r['delay_O']),dM=float(r['delay_M']),dP=float(r['delay_P']),
        cO=float(r['cost_O']),cM=float(r['cost_M']),cP=float(r['cost_P'])) for _,r in rows.iterrows()]
    c=E.Config(start='2027-02-01',n=10000,seed=42,rate=.6561)
    errors,_,order=E.validate(acts,c); assert not errors
    hist=R.HistoricalRainfall(R.load_and_validate())
    first=R.simulate_rainfall(acts,order,c,n=10000,seed=42,multiplier=1.0,historical=hist)
    second=R.simulate_rainfall(acts,order,c,n=10000,seed=42,multiplier=1.0,historical=hist)
    assert np.array_equal(first.delay,second.delay)
    assert np.array_equal(first.extra,second.extra)
