import random, secrets
from sqlmodel import select
from ..storage import get_session
from ..models import AdminConfig

_WORDS = [
    "tui","kiwi","pohutukawa","harbour","beach","waka","kauri","ponga","kepler","southern",
    "albatross","river","island","koru","pounamu","sunrise","sunset","storm","mist","summit",
    "spark","ember","glow","forest","valley","ocean","rimu","totara","manuka","harakeke",
    "kumara","tuatara","alpine","peak","fern","swift","clever","brave","steady","calm",
    "bright","kind","solid","focused","nimble"
]

def _gen_pwd() -> str:
    return f"{random.choice(_WORDS)}-{random.choice(_WORDS)}-{secrets.randbelow(100)}"

def ensure_admin_password() -> None:
    """Ensure an admin password exists and print it to container logs every boot."""
    with get_session() as s:
        cfg = s.exec(select(AdminConfig)).first()
        if not cfg or not cfg.admin_password_plain:
            pwd = _gen_pwd()
            if not cfg:
                from ..models import AdminConfig as AdminCfg
                cfg = AdminCfg(admin_password_plain=pwd)
                s.add(cfg)
            else:
                cfg.admin_password_plain = pwd
            s.commit()
            print(f"[Quickfire] Admin password (generated): {pwd}")
        else:
            print(f"[Quickfire] Admin password: {cfg.admin_password_plain}")
