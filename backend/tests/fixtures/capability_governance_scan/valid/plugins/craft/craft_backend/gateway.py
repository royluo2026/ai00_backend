from .provider import FactoryProvider


class FactoryGateway:
    def create(self, payload):
        return FactoryProvider().create(payload)
