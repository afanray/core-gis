from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    success: bool = True
    status: Optional[str] = "success"
    data: Optional[T] = None
    message: Optional[str] = None

class PaginationMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

class PaginatedResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    success: bool = True
    data: List[T]
    meta: PaginationMeta
