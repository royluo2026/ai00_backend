from .table_names import FACTORY_TABLE


class FactoryRepository:
    table_name = FACTORY_TABLE

    def create(self, payload):
        return {"table": self.table_name, "payload": payload}
