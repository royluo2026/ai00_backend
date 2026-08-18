from .factory_port import FactoryPort


class FactoryProvider:
    def create(self, payload):
        return FactoryPort().create(payload)
