from dataclasses import dataclass


@dataclass
class OperationObject:
    name: str
    self_id: str
    toir_id: str
    object_id: str
    object_type: str
