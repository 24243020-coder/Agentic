# Blood Bank Management System v9

- Adding a donor immediately adds their entered units to Blood Inventory.
- New donors start as Available.
- Blood Requests show matching donors and their current available units.
- Fulfilling a request decreases Blood Inventory and, when a donor is assigned, decreases that donor's available units by the issued amount.
- A donor remains Available while units are above 0 and becomes Unavailable at 0.
- No donation-confirmation step is used in the visible workflow.
- Recent Activity records donor additions and blood issuance.
