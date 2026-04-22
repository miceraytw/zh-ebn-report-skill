"""De-identification detector tests."""

from __future__ import annotations

from zh_ebn_report.utils.deid import scan


def test_clean_text_passes() -> None:
    text = "個案為 70-75 歲男性，因肺炎入院。家屬陪伴下接受照護。"
    assert scan(text).passed


def test_tw_id_detected() -> None:
    text = "身分證 A123456789 的個案⋯⋯"
    report = scan(text)
    assert not report.passed
    assert any(f.category == "TW_ID" for f in report.findings)


def test_mrn_detected() -> None:
    text = "病歷號：12345678"
    report = scan(text)
    assert not report.passed
    assert any(f.category == "MRN" for f in report.findings)


def test_birth_date_detected() -> None:
    text = "出生日期：1955/03/15"
    report = scan(text)
    assert not report.passed
    assert any(f.category == "BIRTH_DATE" for f in report.findings)


def test_phone_detected() -> None:
    text = "連絡電話：0912-345-678"
    report = scan(text)
    assert not report.passed
    assert any(f.category == "TW_PHONE" for f in report.findings)


def test_labeled_name_detected() -> None:
    text = "姓名：王小明"
    report = scan(text)
    assert not report.passed
    assert any(f.category == "NAME" for f in report.findings)
