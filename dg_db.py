#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Apr 25 00:56:57 2025

@author: nikita
"""

role_based_db = {
        "analyst": {
            "CustomerDB": "cust_spoc@company.com",
            "AnalyticsDB": "analytics_spoc@company.com"
        },
        "admin": {
            "FinanceDB": "fin_spoc@company.com",
            "CustomerDB": "cust_spoc@company.com"
        },
        "teller": {
            "CustomerDB": "cust_spoc@company.com"
        }
    }