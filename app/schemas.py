from pydantic import BaseModel, Field
from typing import Optional


class MaterialBase(BaseModel):
    name: str = Field(..., max_length=255)
    measurement_unit_id: int = Field(default=1, ge=1)
    description: Optional[str] = None


class MaterialCreate(MaterialBase):
    pass


class MaterialUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    measurement_unit_id: Optional[int] = Field(None, ge=1)
    description: Optional[str] = None


class MaterialResponse(MaterialBase):
    id: int
    is_active: bool
    quantity: float = 0.0

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