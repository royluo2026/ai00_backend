from uuid import uuid4

def next_gid() -> str:
    return f"ont_{uuid4().hex}"

