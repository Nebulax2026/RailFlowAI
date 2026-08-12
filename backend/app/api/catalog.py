from fastapi import APIRouter

from app.domain.catalog import catalog_response

router = APIRouter()


@router.get("")
def get_catalog() -> dict:
    return catalog_response()
