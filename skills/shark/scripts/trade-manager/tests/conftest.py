"""Shared test fixtures for the trade-manager suite."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The kit fork drops the Cloud Run kill-switch lock entirely (paper-only by
# construction), so there is no control check to default off — broker.enter()
# places orders without any network call beyond the broker itself.
