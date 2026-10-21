"""Legacy replica settings cannot restart local project writers."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_settings
import lumen_connect
from tools_data import Library

class RetirementTest(unittest.TestCase):

    def test_connector_has_no_replica_launcher(self):
        self.assertFalse(hasattr(lumen_connect,'sync_projects'))
        self.assertFalse(hasattr(sync_settings,'project_library'))
