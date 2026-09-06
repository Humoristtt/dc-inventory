from fastapi import HTTPException, Request, status


def require_real_inventory_mutations_enabled(request: Request) -> None:
    settings = request.app.state.settings

    if settings.real_inventory_mutations_enabled:
        return

    raise HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail={
            "code": "real_inventory_mutations_disabled",
            "message": (
                "real inventory mutations are disabled by deployment policy"
            ),
        },
    )
