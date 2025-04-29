#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 24 23:08:13 2025

@author: nikita
"""

# Define task dictionary
tasks_db = {
    "download": {
        "description": "download applications",
        "actions": {
            "data_visualization": ["PowerBI", "Tableau"],
            "coding_tools": ["Python", "R", "Jupyter Notebook"],
            "databases": ["SQL Developer", "MongoDB Compass"],
            "security_tools": ["Okta Admin", "Splunk"],
            "management": ["ServiceNow", "Jira"],
            "transaction_tools": ["CoreBank App", "ChequeScan"],
            "reporting": ["QuickReports"]
        }
    },
    "access": {
        "description": "access database",
        "actions": {}
    },
    "update": {
        "description": "update user info",
        "actions": {}
    },
    "summarize": {
        "description": "summarize pdf",
        "actions": {}
    },
    "compliance": {
        "description": "compliance information",
        "actions": {}
    },
    "field_mapping": {
        "description": "find field names or table name for a given field",
        "actions": {}
    }
}
