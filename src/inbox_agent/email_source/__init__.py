"""Email sources behind one interface.

``SyntheticEmailSource`` (default, offline, fake data) and a guarded read-only
``GmailEmailSource`` stub. Real Gmail is never required to run the project.
"""

from inbox_agent.email_source.base import EmailSource
from inbox_agent.email_source.factory import build_email_source
from inbox_agent.email_source.synthetic import SyntheticEmailSource

__all__ = ["EmailSource", "SyntheticEmailSource", "build_email_source"]
