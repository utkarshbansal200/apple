"""Course-brief check: simulated three-point means vs hand PERT means (O+4M+P)/6."""
import pandas as pd
import engine as E

def _load():
    rows = pd.read_csv('sample_activities.csv').fillna('')
    acts = [E.Activity(id=str(r['id']), name=str(r['name']), dur=float(r['duration']), cost=float(r['cost']),
            pre=[s for s in str(r['predecessors']).split(';') if s], dO=float(r['delay_O']), dM=float(r['delay_M']),
            dP=float(r['delay_P']), cO=float(r['cost_O']), cM=float(r['cost_M']), cP=float(r['cost_P']))
            for _, r in rows.iterrows()]
    cfg = E.Config()
    _, _, order = E.validate(acts, cfg)
    return acts, order, cfg

def test_activity_means_match_hand_pert():
    acts, order, cfg = _load()
    r = E.simulate(acts, order, cfg, n=20000, engine='legacy')
    for i, a in enumerate(acts):
        assert abs(r.act_delay[i].mean() - E.pert_mean(a.dO, a.dM, a.dP)) < 0.05
        assert abs(r.act_cost[i].mean() - E.pert_mean(a.cO, a.cM, a.cP)) < 0.06

def test_project_hand_sum_is_lower_bound():
    acts, order, cfg = _load()
    r = E.simulate(acts, order, cfg, n=20000, engine='legacy')
    _, cp, _ = E.floats_and_critical_path(acts, order)
    h = E.hand_pert_project(acts, cp, cfg.rho, cfg.rate)
    assert r.delay.mean() >= h['mean_delay'] - 0.1
