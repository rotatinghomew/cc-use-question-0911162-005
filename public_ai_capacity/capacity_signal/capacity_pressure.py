from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

@dataclass(frozen=True)
class DomainSignal:
    code: str
    score: float
    severity: str
    evidence: dict[str, Any]

def number(payload: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(payload.get(key, default))
    except (TypeError, ValueError):
        return default
    return default if value != value or value in (float('inf'), float('-inf')) else value

def ratio(payload: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    value = number(payload, key, default)
    if value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))

def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

def capacity_pressure(payload:Mapping[str,Any])->DomainSignal:
    latency=min(1.0,number(payload,'latency_ms')/5000.0); queue=max(0.0,number(payload,'request_queue')); load=ratio(payload,'capacity_load'); errors=ratio(payload,'error_rate')
    units=max(1.0,number(payload,'capacity_units',1)); priority=ratio(payload,'priority'); saturation=min(1.0,queue/units)
    pressure=clamp(latency*.18+saturation*.27+load*.25+errors*.22+priority*.08)
    status=str(payload.get('service_status','')).lower(); severity='critical' if status in {'failed','outage','down'} or pressure>=.75 else 'warning' if pressure>=.45 else 'info'
    return DomainSignal('capacity_pressure',pressure,severity,{'latency_pressure':latency,'saturation':saturation,'load':load,'error_rate':errors})

def peer_distribution(records:Iterable[Any],group_field:str='region_code')->dict[str,Any]:
    groups={}
    for r in records:
        p=getattr(r,'payload',r); groups.setdefault(str(p.get(group_field,'unknown')),[]).append(capacity_pressure(p).score)
    peaks={k:max(v) for k,v in groups.items()}
    return {'groups':peaks,'count':sum(len(v) for v in groups.values()),'critical_regions':sum(v>=.75 for v in peaks.values())}

def augment_context(record:Any,repository:Any)->dict[str,Any]:
    signal=capacity_pressure(record.payload); peers=peer_distribution(repository.list_records())
    return {'domain_signal':signal.score,'domain_severity':signal.severity,'critical_regions':peers['critical_regions'],'peer_count':peers['count']}
