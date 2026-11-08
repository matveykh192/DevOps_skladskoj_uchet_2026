from pydantic import BaseModel, Field
from typing import Optional


class MaterialBase(BaseModel):
    name: str = Field(..., max_length=255)
    measurement_unit_id: int = Field(default=1, ge=1)
    description: Optional[str] = None
    minimum_stock: float = Field(default=0, ge=0, le=999999999.999)


class MaterialCreate(MaterialBase):
    pass


class MaterialUpdate(BaseModel):
    minimum_stock: Optional[float] = Field(default=None, ge=0, le=999999999.999)
    name: Optional[str] = Field(None, max_length=255)
    measurement_unit_id: Optional[int] = Field(None, ge=1)
    description: Optional[str] = None


class MaterialResponse(MaterialBase):
    id: int
    is_active: bool
    quantity: float = 0.0
    minimum_stock: float = 0.0
    is_below_minimum: bool = False

    class Config:
        from_attributes = True


class SupplierBase(BaseModel):
    name: str = Field(..., max_length=255)
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class SupplierResponse(SupplierBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True
