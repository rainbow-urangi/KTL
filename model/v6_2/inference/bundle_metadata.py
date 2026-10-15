"""Read tensor descriptors without loading weights or executing checkpoint globals."""
import io
import pickle
import zipfile
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class TensorDescriptor:
    storage: tuple
    offset: int
    shape: tuple
    stride: tuple
    requires_grad: bool
    hooks: object


class MetadataReader(pickle.Unpickler):
    def find_class(self, module, name):
        allowed = {
            ("collections", "OrderedDict"): OrderedDict,
            ("torch", "FloatStorage"): "float32",
            ("torch._utils", "_rebuild_tensor_v2"): TensorDescriptor,
        }
        if (module, name) not in allowed:
            raise ValueError(f"허용되지 않은 checkpoint 타입: {module}.{name}")
        return allowed[module, name]

    def persistent_load(self, identifier):
        if not isinstance(identifier, tuple) or len(identifier) != 5 or identifier[0] != "storage":
            raise ValueError("올바르지 않은 tensor storage 참조")
        return identifier


def read_bundle_metadata(path):
    with zipfile.ZipFile(path) as archive:
        entries = [n for n in archive.namelist() if n.endswith("/data.pkl")]
        if len(entries) != 1:
            raise ValueError("checkpoint metadata가 하나여야 합니다")
        return MetadataReader(io.BytesIO(archive.read(entries[0]))).load()
