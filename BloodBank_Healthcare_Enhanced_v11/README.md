# BloodLink Blood Bank Management System v8

This version fixes donor availability and donor selection for older databases.

## Run

```powershell
cd "C:\Users\AKSHAYA JEYAGOPAL\Downloads\BloodBank_Healthcare_Enhanced_v8\bloodbank_v5"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000

### Donor workflow
1. Add donor: donor is immediately Available.
2. The donor is immediately marked Available with the entered unit count.
3. The entered units are immediately added to Blood Inventory.
4. When a request is fulfilled, inventory and the selected donor's available units both decrease; the donor becomes Unavailable only when their units reach 0.
5. Blood Requests only lists currently Available donors with the selected blood group.
