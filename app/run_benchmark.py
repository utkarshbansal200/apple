"""Reproduce published corrected-model simulation outputs without Streamlit."""
import json
from pathlib import Path
import pandas as pd
import numpy as np
import engine as E
import rainfall_model as R

root=Path(__file__).parent
rows=pd.read_csv(root/'sample_activities.csv').fillna('')
acts=[E.Activity(id=str(r['id']),name=str(r['name']),dur=float(r['duration']),cost=float(r['cost']),pre=[s for s in str(r['predecessors']).split(';') if s],dO=float(r['delay_O']),dM=float(r['delay_M']),dP=float(r['delay_P']),cO=float(r['cost_O']),cM=float(r['cost_M']),cP=float(r['cost_P'])) for _,r in rows.iterrows()]
c=E.Config()
errors,warnings,order=E.validate(acts,c)
if errors:raise ValueError(errors)
out=root/'results';out.mkdir(exist_ok=True)
rf=R.HistoricalRainfall(R.load_and_validate())
all_summaries={}
for label,mult in [('Mild',0.6),('Typical',1.0),('Severe',1.5)]:
    run=R.simulate_rainfall(acts,order,c,n=10000,multiplier=mult,historical=rf,label=label)
    summ=E.summarise(run)
    entry={'n':run.n,'seed':c.seed,'start':c.start,'baseline_days':run.base,'baseline_cost_lakh':c.base,'mean_delay_days':summ['mean_delay'],'median_delay_days':float(np.median(run.delay)), 'p50_delay_days':float(np.percentile(run.delay,50)), 'p80_delay_days':float(np.percentile(run.delay,80)), 'p90_delay_days':float(np.percentile(run.delay,90)), 'mean_additional_cost_lakh':summ['mean_cost'], 'median_additional_cost_lakh':float(np.median(run.extra)), 'p50_cost_lakh':float(np.percentile(run.extra,50)), 'p80_cost_lakh':float(np.percentile(run.extra,80)), 'p90_cost_lakh':float(np.percentile(run.extra,90)), 'p_delay_over_30days':float((run.delay>30).mean()),'p_cost_over_40lakh':float((run.extra>40).mean()),'per_activity_mean_lost_days':{a.id:float(run.act_delay[i].mean()) for i,a in enumerate(acts)}, 'per_activity_mean_cost_lakh':{a.id:float(run.act_cost[i].mean()) for i,a in enumerate(acts)}, 'per_activity_mean_rain_mm':{a.id:float(run.rain_exposure[i].mean()) for i,a in enumerate(acts)}}
    all_summaries[label]=entry
    if label=='Typical':
        pd.DataFrame({'additional_delay_days':run.delay,'additional_cost_lakh':run.extra,'sampled_historical_start_year':run.historical_years}).to_csv(out/'typical_10000_draws.csv',index=False)
        pd.DataFrame({'activity':[a.id for a in acts],'mean_lost_days':run.act_delay.mean(axis=1),'mean_extra_cost_lakh':run.act_cost.mean(axis=1),'mean_rain_mm':run.rain_exposure.mean(axis=1)}).to_csv(out/'activity_contributions.csv',index=False)
(out/'simulation_summary.json').write_text(json.dumps(all_summaries,indent=2))
(out/'rainfall_diagnostics.json').write_text(json.dumps(R.diagnostics(R.load_and_validate(), 'Bundled historical rainfall CSV'),indent=2))
print(json.dumps({k:{key:round(v[key],3) for key in ['mean_delay_days','p80_delay_days','mean_additional_cost_lakh','p80_cost_lakh']} for k,v in all_summaries.items()},indent=2))
