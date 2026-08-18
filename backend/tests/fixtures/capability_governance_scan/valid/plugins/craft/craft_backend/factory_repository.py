class FactoryRepository:
    table_name = "workmanship_craft_bop_factories"

    def create(self, payload):
        return {"table": self.table_name, "payload": payload}
