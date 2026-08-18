from .factory_repository import FactoryRepository


class FactoryPort:
    def create(self, payload):
        return FactoryRepository().create(payload)
