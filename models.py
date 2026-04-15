from pydantic import BaseModel, Field, HttpUrl, validator
from typing import List, Optional, Any, Union

class PaperMetadata(BaseModel):
    id: Optional[str] = None
    title: str = Field(default="")
    authors: List[str] = Field(default_factory=list)
    year: Optional[Union[str, int]] = None
    doi: Optional[str] = None
    cited_by_count: int = Field(default=0)
    is_oa: bool = Field(default=False)
    open_access_pdf: Optional[str] = None
    abstract: Optional[str] = None

class AuthorProfile(BaseModel):
    id: Optional[str] = None
    display_name: str = Field(default="Unknown")
    orcid: Optional[str] = None
    works_count: int = Field(default=0)
    cited_by_count: int = Field(default=0)
    h_index: int = Field(default=0)
    i10_index: int = Field(default=0)
    last_institution: str = Field(default="Unknown")
    x_concepts: List[str] = Field(default_factory=list)

class TopicItem(BaseModel):
    id: Optional[str] = None
    display_name: str = Field(default="")
    subfield: str = Field(default="")
    field: str = Field(default="")
    domain: str = Field(default="")
    works_count: int = Field(default=0)
    cited_by_count: int = Field(default=0)
    description: Optional[str] = None
    
class CitationResponse(BaseModel):
    title: str = Field(default="")
    authors: List[str] = Field(default_factory=list)
    year: Optional[Union[str, int]] = None
    doi: Optional[str] = None
    cited_by_count: int = Field(default=0)
    
class AuthorWork(BaseModel):
    title: str = Field(default="")
    year: Optional[Union[str, int]] = None
    doi: Optional[str] = None
    cited_by_count: int = Field(default=0)
