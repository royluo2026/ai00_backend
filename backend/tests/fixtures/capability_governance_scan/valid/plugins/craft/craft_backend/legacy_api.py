class FactoryLegacyApi:
    pass


@router.get("/legacy")
def legacy_factory_route():
    return {"ok": True}
