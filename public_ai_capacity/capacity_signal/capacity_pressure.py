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
    units=number(payload,'capacity_units',0.0); priority=ratio(payload,'priority')
    allocatable=units>0.0
    # saturation is a ratio against available units: without units there is no
    # ratio to report. Never substitute a 1-unit denominator, which would fake
    # a normal "fully loaded" reading for a window that has no capacity at all.
    saturation=min(1.0,queue/units) if allocatable else None
    saturation_term=saturation if allocatable else 1.0
    pressure=clamp(latency*.18+saturation_term*.27+load*.25+errors*.22+priority*.08)
    status=str(payload.get('service_status','')).lower(); severity='critical' if not allocatable or status in {'failed','outage','down'} or pressure>=.75 else 'warning' if pressure>=.45 else 'info'
    return DomainSignal('capacity_pressure',pressure,severity,{'latency_pressure':latency,'saturation':saturation,'load':load,'error_rate':errors,
                                                             'capacity_units':units,'allocatable':allocatable,
                                                             'capacity_state':'unavailable' if not allocatable else ('overloaded' if saturation_term>=1.0 else 'available')})

def peer_distribution(records:Iterable[Any],group_field:str='region_code')->dict[str,Any]:
    groups={}
    for r in records:
        p=getattr(r,'payload',r); groups.setdefault(str(p.get(group_field,'unknown')),[]).append(capacity_pressure(p))
    peaks={k:max(item.score for item in items) for k,items in groups.items()}
    unavailable={k for k,items in groups.items() if any(not item.evidence.get('allocatable', True) for item in items)}
    return {'groups':peaks,'count':sum(len(v) for v in groups.values()),'critical_regions':sum(v>=.75 or k in unavailable for k,v in peaks.items()),
            'unavailable_regions':len(unavailable)}

def augment_context(record:Any,repository:Any)->dict[str,Any]:
    signal=capacity_pressure(record.payload); peers=peer_distribution(repository.list_records())
    return {'domain_signal':signal.score,'domain_severity':signal.severity,'critical_regions':peers['critical_regions'],'peer_count':peers['count'],
            'signal_allocatable':signal.evidence['allocatable'],'signal_capacity_state':signal.evidence['capacity_state'],
            'unavailable_regions':peers['unavailable_regions']}
