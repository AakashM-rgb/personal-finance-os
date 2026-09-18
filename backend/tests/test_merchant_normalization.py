from app.services.merchant_normalization import normalize_merchant


def test_swiggy_plain() -> None:
    result = normalize_merchant("UPI/DR/399/SWIGGY/paytm@ybl/Swiggy Order")
    assert result.canonical_name == "Swiggy"
    assert result.recognized is True


def test_swiggy_instamart_variant() -> None:
    result = normalize_merchant("UPI/DR/499/SWIGGY INSTAMART/paytm@ybl/Grocery")
    assert result.canonical_name == "Swiggy"
    assert result.recognized is True


def test_swiggy_pvt_ltd_variant() -> None:
    result = normalize_merchant("UPI/DR/399/SWIGGY PVT LTD/paytm@ybl/Order")
    assert result.canonical_name == "Swiggy"
    assert result.recognized is True


def test_amazon_from_amzn_mktplace() -> None:
    result = normalize_merchant("UPI/DR/850/AMZN MKTPLACE/amazon@icici/Online Purchase")
    assert result.canonical_name == "Amazon"
    assert result.recognized is True


def test_netflix_from_dotcom_narration() -> None:
    result = normalize_merchant("NETFLIX.COM")
    assert result.canonical_name == "Netflix"
    assert result.recognized is True


def test_neft_rent_payment_unknown_merchant_preserved() -> None:
    result = normalize_merchant("NEFT/DR/N123456789012/RENT PAYMENT LANDLORD")
    assert result.recognized is False
    # Unknown merchants must remain identifiable, not discarded or mis-mapped.
    assert result.canonical_name == "Rent Payment Landlord"


def test_imps_salary_unknown_merchant_preserved() -> None:
    result = normalize_merchant("IMPS/CR/987654321098/SALARY ACME CORP PVT LTD")
    assert result.recognized is False
    assert result.canonical_name == "Salary Acme Corp"


def test_messy_upi_noise_is_stripped() -> None:
    result = normalize_merchant("UPI/DR/120/BESCOM BBMP/bescom@sbi/Electricity Bill")
    # Not a known merchant alias, but the mode/direction/reference/VPA noise
    # must still be gone from the fallback display name.
    assert "UPI" not in result.canonical_name.upper()
    assert "DR" not in result.canonical_name.upper().split()
    assert "120" not in result.canonical_name
    assert "@" not in result.canonical_name


def test_unknown_merchant_is_never_mapped_to_a_known_one() -> None:
    result = normalize_merchant("UPI/DR/200/RANDOM LOCAL STORE/xyz@upi/Purchase")
    assert result.recognized is False
    assert result.canonical_name not in {"Swiggy", "Amazon", "Netflix", "Uber", "Ola"}


def test_empty_narration_is_handled_safely() -> None:
    result = normalize_merchant("")
    assert result.recognized is False
    assert result.canonical_name == "Unknown Merchant"


def test_whitespace_only_narration_is_handled_safely() -> None:
    result = normalize_merchant("   ")
    assert result.recognized is False
    assert result.canonical_name == "Unknown Merchant"


def test_uber_recognized() -> None:
    result = normalize_merchant("UPI/DR/250/UBER INDIA SYSTEMS/uber@icici/Uber Trip")
    assert result.canonical_name == "Uber"
    assert result.recognized is True


def test_normalization_is_deterministic() -> None:
    narration = "UPI/DR/399/SWIGGY/paytm@ybl/Swiggy Order"
    assert normalize_merchant(narration) == normalize_merchant(narration)
