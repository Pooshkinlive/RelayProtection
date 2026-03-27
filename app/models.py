from dataclasses import dataclass
from typing import Dict

@dataclass
class NetworkElement:
    id: int
    name: str
    element_type: str
    parameters: Dict[str, float]

@dataclass
class ProtectionSetting:
    id: int
    element_id: int
    protection_type: str
    setting_value: float
    operating_time: float
    sensitivity: float
