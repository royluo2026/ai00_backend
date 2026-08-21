@router.post("/factories")
def create_factory(payload):
    return invoke_capability("craft.bop.factory.create", payload)


def _invoke(write=False):
    return invoke_capability(
        capability_id="craft.bop.factory.create" if write else "craft.bop.factory.create",
        payload={},
    )


@router.post("/factories/helper")
def create_factory_via_helper(payload):
    return _invoke(write=True)


@router.get("/factories/retired", status_code=410)
def retired_factory_route():
    raise HTTPException(410, "retired")


class CreateFactoryBody:
    pass
