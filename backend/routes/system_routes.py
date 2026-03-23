from fastapi import APIRouter, Depends

from ..container import inject_container
from .response_utils import standardized_success


router = APIRouter(tags=["system"])


@router.get("/health")
def health(container=Depends(inject_container)):
    return standardized_success(container.system_service.health())


@router.get("/metrics")
def metrics(container=Depends(inject_container)):
    return standardized_success(container.system_service.metrics())


@router.get("/status")
def status(container=Depends(inject_container)):
    return standardized_success(container.system_service.status())
