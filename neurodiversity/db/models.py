"""Pydantic models mirroring supabase/schema.sql. Field names and enum values match the
SQL schema exactly so these can be used directly for reads and writes with no translation
layer. Phase 1 covers only what the thin end-to-end slice needs: papers, study_facts,
quality_fields, quality_checks, chunks. The rest (constructs, measures, claims,
community_accounts, external_records, sessions, turns) follow once Phase 1 is proven.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DesignType(str, Enum):
    imaging_case_control = "imaging_case_control"
    trial = "trial"
    qualitative = "qualitative"
    psychometric_validation = "psychometric_validation"
    observational_cohort = "observational_cohort"
    other_unclassified = "other_unclassified"


class QualityCheckStatus(str, Enum):
    reported = "reported"
    absent = "absent"
    not_applicable = "not_applicable"
    unchecked = "unchecked"


class PaperLicense(str, Enum):
    cc_by = "cc_by"
    cc_by_nc = "cc_by_nc"
    cc_by_nc_nd = "cc_by_nc_nd"
    closed = "closed"
    unknown = "unknown"


class PublicationStatus(str, Enum):
    published = "published"
    preprint = "preprint"
    in_press = "in_press"


class Paper(BaseModel):
    id: Optional[UUID] = None
    doi: Optional[str] = None
    pubmed_id: Optional[str] = None
    pmc_id: Optional[str] = None
    title: str
    abstract: Optional[str] = None
    publication_year: Optional[int] = None
    journal: Optional[str] = None
    license: PaperLicense = PaperLicense.unknown
    has_fulltext: bool = False
    full_text: Optional[str] = None
    publication_status: PublicationStatus = PublicationStatus.published
    retracted: bool = False
    retracted_checked_at: Optional[datetime] = None


class StudyFacts(BaseModel):
    paper_id: UUID
    design_type: Optional[DesignType] = None
    n_clinical: Optional[int] = None
    n_control: Optional[int] = None
    n_total: Optional[int] = None
    site_count: Optional[int] = None
    modality: Optional[str] = None
    population: Optional[str] = None
    age_range: Optional[str] = None
    cohort_name: Optional[str] = None
    preregistration: Optional[bool] = None
    data_availability: Optional[bool] = None


class QualityField(BaseModel):
    id: str
    auditor: str
    name: str
    rationale: str
    applies_to: list[DesignType]
    display_order: int = 0


class QualityCheck(BaseModel):
    id: Optional[UUID] = None
    paper_id: UUID
    field_id: str
    status: QualityCheckStatus = QualityCheckStatus.unchecked
    evidence_snippet: Optional[str] = None
    location: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    priority: bool = False
    checked_at: Optional[datetime] = None


class Chunk(BaseModel):
    id: Optional[UUID] = None
    paper_id: UUID
    section: Optional[str] = None
    chunk_index: int
    text: str
    embedding: Optional[list[float]] = None
