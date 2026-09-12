from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UnitRecord(Base):
    __tablename__ = "units"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    unit_type: Mapped[str] = mapped_column(String(30))
    leases: Mapped[list[LeaseRecord]] = relationship(back_populates="unit", cascade="all, delete-orphan")
    meters: Mapped[list[MeterReadingRecord]] = relationship(back_populates="unit", cascade="all, delete-orphan")


class TenantRecord(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    identity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    identity_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    phones: Mapped[list[TenantPhoneRecord]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    leases: Mapped[list[LeaseRecord]] = relationship(back_populates="tenant")
    attachments: Mapped[list[FileRecord]] = relationship(back_populates="tenant")


class TenantPhoneRecord(Base):
    __tablename__ = "tenant_phones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    phone: Mapped[str] = mapped_column(String(50))
    tenant: Mapped[TenantRecord] = relationship(back_populates="phones")


class LeaseRecord(Base):
    __tablename__ = "leases"
    __table_args__ = (UniqueConstraint("unit_id", "tenant_id", "start_date", name="uq_lease_start"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    rent_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    due_day: Mapped[int] = mapped_column(Integer)
    payment_method: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    unit: Mapped[UnitRecord] = relationship(back_populates="leases")
    tenant: Mapped[TenantRecord] = relationship(back_populates="leases")
    witnesses: Mapped[list[WitnessRecord]] = relationship(back_populates="lease", cascade="all, delete-orphan")
    attachments: Mapped[list[FileRecord]] = relationship(back_populates="lease")


class WitnessRecord(Base):
    __tablename__ = "witnesses"
    __table_args__ = (UniqueConstraint("lease_id", "witness_order", name="uq_lease_witness_order"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lease_id: Mapped[int] = mapped_column(ForeignKey("leases.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50))
    witness_order: Mapped[int] = mapped_column(Integer)
    lease: Mapped[LeaseRecord] = relationship(back_populates="witnesses")


class MeterReadingRecord(Base):
    __tablename__ = "meter_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    meter_type: Mapped[str] = mapped_column(String(30), index=True)
    reading_date: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit: Mapped[UnitRecord] = relationship(back_populates="meters")


class BuildingMeterReadingRecord(Base):
    __tablename__ = "building_meter_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meter_type: Mapped[str] = mapped_column(String(30), index=True)
    reading_date: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 3))


class InvoiceRecord(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    electricity_previous: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    electricity_current: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    electricity_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    water_previous: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    water_current: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    water_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    shared_expenses: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    arrears: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentRecord(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    payment_method: Mapped[str] = mapped_column(String(100))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AuditLogRecord(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FileRecord(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    lease_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leases.id"), nullable=True, index=True)
    attachment_type: Mapped[str] = mapped_column(String(50), default="OTHER", index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    tenant: Mapped[Optional[TenantRecord]] = relationship(back_populates="attachments")
    lease: Mapped[Optional[LeaseRecord]] = relationship(back_populates="attachments")
