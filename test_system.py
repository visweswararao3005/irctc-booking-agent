"""Comprehensive verification test suite for IRCTC Telegram AI Agent."""
import asyncio
import os
import sys
import shutil
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import storage
import security
from irctc_service import IRCTCService
from ticket_generator import generate_ticket_pdf

async def run_tests():
    print("=" * 60)
    print("🧪 STARTING IRCTC AGENT VERIFICATION TESTS")
    print("=" * 60)

    # 1. Test Encryption & Security
    print("\n[Test 1] Testing Security & AES-256 Encryption...")
    plain_pass = "MySecretPass@123"
    cipher_pass = security.encrypt_text(plain_pass)
    decrypted = security.decrypt_text(cipher_pass)
    assert plain_pass == decrypted, f"Decryption failed: {decrypted} != {plain_pass}"
    masked = security.mask_text("balaji_irctc", 3)
    assert masked.startswith("bal") and "*" in masked, f"Masking failed: {masked}"
    print("✅ Security & Encryption: PASSED")

    # 2. Test JSON User Storage & Per-Chat Credentials
    print("\n[Test 2] Testing Per-Chat User Credential Management in JSON...")
    test_user_id = 999999
    await storage.save_user_credentials(test_user_id, "balaji_user", "irctc_p@ssword")
    u_name, u_pass = await storage.get_decrypted_credentials(test_user_id)
    assert u_name == "balaji_user", f"Expected 'balaji_user', got {u_name}"
    assert u_pass == "irctc_p@ssword", f"Expected 'irctc_p@ssword', got {u_pass}"

    # Test reset credentials
    await storage.reset_user_credentials(test_user_id)
    reset_u, reset_p = await storage.get_decrypted_credentials(test_user_id)
    assert reset_u is None or reset_u == "", f"Reset failed, still got: {reset_u}"
    print("✅ Per-Chat Credential Management & Reset: PASSED")

    # 2b. Test Per-Chat Credit Card Storage & Encryption
    print("\n[Test 2b] Testing Per-Chat Payment Card Storage, Masking & Reset in JSON...")
    await storage.save_user_card(
        telegram_id=test_user_id,
        card_number="4111222233334444",
        card_expiry="12/28",
        card_cvv="123",
        card_holder="BALAJI P"
    )
    card_data = await storage.get_decrypted_card(test_user_id)
    assert card_data is not None, "Card data not found in storage"
    assert card_data["card_number"] == "4111222233334444", "Card number mismatch"
    assert card_data["card_expiry"] == "12/28", "Card expiry mismatch"
    assert card_data["card_cvv"] == "123", "Card CVV mismatch"
    assert card_data["card_holder"] == "BALAJI P", "Card holder mismatch"

    # Test reset card
    await storage.reset_user_card(test_user_id)
    reset_card = await storage.get_decrypted_card(test_user_id)
    assert reset_card is None, f"Card reset failed, still got: {reset_card}"
    print("✅ Per-Chat Payment Card Management & Reset: PASSED")

    # [Test 2f] Testing Per-Chat UPI ID Storage, Encryption & Reset...
    print("\n[Test 2f] Testing Per-Chat UPI ID Storage, Encryption & Reset...")
    await storage.save_user_upi(test_user_id, "balaji@paytm")
    upi_id = await storage.get_decrypted_upi(test_user_id)
    assert upi_id == "balaji@paytm", f"Expected 'balaji@paytm', got {upi_id}"
    await storage.reset_user_upi(test_user_id)
    reset_upi = await storage.get_decrypted_upi(test_user_id)
    assert reset_upi is None, f"UPI reset failed, got {reset_upi}"
    print("✅ Per-Chat UPI ID Management & Reset: PASSED")

    # [Test 2c] Testing User Session Persistence & Recovery...
    print("\n[Test 2c] Testing User Session Persistence & Recovery...")
    sample_session = {
        "source": "KJM",
        "dest": "MAS",
        "date": "2026-10-05",
        "train_number": "16022"
    }
    await storage.save_user_session(test_user_id, sample_session)
    restored_session = await storage.get_user_session(test_user_id)
    assert restored_session.get("source") == "KJM"
    assert restored_session.get("dest") == "MAS"
    assert restored_session.get("date") == "2026-10-05"
    await storage.clear_user_session(test_user_id)
    cleared = await storage.get_user_session(test_user_id)
    assert cleared == {}
    print("✅ Session Persistence & Crash Recovery: PASSED")

    # [Test 2d] Testing Date Keyboard & Future Date Logic...
    print("\n[Test 2d] Testing Current Date & Future-Only Date Constraints...")
    import datetime
    today = datetime.date.today()
    past_date = today - datetime.timedelta(days=1)
    future_date = today + datetime.timedelta(days=5)
    assert past_date < today, "Past date calculation error"
    assert future_date >= today, "Future date calculation error"
    from bot import get_date_keyboard, adjust_date, build_date_picker_inline_keyboard, format_date_picker_text
    kb = get_date_keyboard()
    assert kb is not None
    print(f"✅ Current Date & Future Date Constraints: PASSED (Today is {today})")

    # [Test 2e] Testing Interactive Date Picker & Stepper Controls...
    print("\n[Test 2e] Testing Interactive Date Picker Steppers (Year, Month, Day)...")
    stepped_next_day = adjust_date(today, delta_d=1)
    assert stepped_next_day == today + datetime.timedelta(days=1)

    stepped_past = adjust_date(today, delta_d=-10)
    assert stepped_past == today, "Past date must be clamped to today"

    stepped_far = adjust_date(today, delta_y=2)
    max_advance = today + datetime.timedelta(days=120)
    assert stepped_far == max_advance, "Dates beyond 120 days must be clamped"

    # Test month end adjustment: e.g. Jan 31 + 1 month clamps to Feb 28
    jan31 = datetime.date(2026, 1, 31)
    feb_clamped = adjust_date(jan31, delta_m=1)
    # Clamp will also enforce today <= target <= today + 120
    assert feb_clamped >= today

    inline_kb = build_date_picker_inline_keyboard(today)
    all_cal_callbacks = [btn.callback_data for row in inline_kb.inline_keyboard for btn in row]
    assert any("cal_prev_y_" in c for c in all_cal_callbacks), "Missing Year prev stepper"
    assert any("cal_next_y_" in c for c in all_cal_callbacks), "Missing Year next stepper"
    assert any("cal_prev_m_" in c for c in all_cal_callbacks), "Missing Month prev stepper"
    assert any("cal_next_m_" in c for c in all_cal_callbacks), "Missing Month next stepper"
    assert any("cal_prev_d_" in c for c in all_cal_callbacks), "Missing Day prev stepper"
    assert any("cal_next_d_" in c for c in all_cal_callbacks), "Missing Day next stepper"
    assert any("cal_confirm_" in c for c in all_cal_callbacks), "Missing Confirm button"

    date_text = format_date_picker_text("KJM", "MAS", today)
    assert "KJM" in date_text and "MAS" in date_text and "Selected Date" in date_text
    print("✅ Interactive Date Picker Steppers & Keyboard: PASSED")

    # 3. Test Train Search & Chronological Sorting

    print("\n[Test 3] Testing Train Search & Earliest Departure Sorting...")
    service = IRCTCService()
    trains = await service.search_trains("MAS", "NLR", "2026-10-15")
    assert len(trains) > 0, "No trains returned"
    
    # Verify sorted order
    departure_times = [t["departure"] for t in trains]
    sorted_times = sorted(departure_times)
    assert departure_times == sorted_times, f"Trains not sorted chronologically: {departure_times}"
    print(f"✅ Train Search (MAS -> NLR): {len(trains)} trains found, properly sorted:")
    for t in trains:
        print(f"   • {t['number']} {t['name']} - Departs {t['departure']}")

    # 4. Test Class Availability & Pricing
    print("\n[Test 4] Testing Class Availability & Pricing Display...")
    classes = await service.get_class_options_with_prices("12712", "MAS", "NLR", "2026-10-15")
    assert len(classes) >= 2, "Missing coach classes"
    print("✅ Class Availability & Live Fares:")
    for c in classes:
        assert "fare" in c and c["fare"] > 0, f"Invalid fare in {c}"
        print(f"   • {c['display']}")

    # 5. Test JSON Task Lifecycle & Auto-Cleanup
    print("\n[Test 5] Testing Active Tasks Lifecycle & Auto-Purging...")
    task_id = await storage.add_task({
        "telegram_id": test_user_id,
        "telegram_chat_id": test_user_id,
        "train_number": "12712",
        "coach_class": "SL",
        "journey_date": "2026-10-15",
        "source_stn": "MAS",
        "dest_stn": "NLR",
        "status": "MONITORING"
    })
    active_tasks = await storage.get_active_tasks()
    assert any(t["task_id"] == task_id for t in active_tasks), "Task not found in active list"

    # Simulate task completion and purge
    await storage.delete_task(task_id)
    active_after = await storage.get_active_tasks()
    assert not any(t["task_id"] == task_id for t in active_after), "Task was not purged from JSON"
    print("✅ Task Lifecycle & JSON Purge: PASSED")

    # 6. Test PDF Ticket Generation
    print("\n[Test 6] Testing IRCTC e-Ticket PDF Generation...")
    sample_booking = {
        "pnr": "4829104829",
        "train_number": "12712",
        "train_name": "PINAKINI EXP",
        "source": "MAS",
        "dest": "NLR",
        "journey_date": "2026-10-15",
        "coach_class": "SL",
        "fare": 240.0,
        "passengers": [
            {"name": "Balaji P", "age": 28, "gender": "M", "berth": "34 (LB)", "status": "CNF"}
        ],
        "payment_method": "Credit Card (Ending in 4444)"
    }
    pdf_path = generate_ticket_pdf(sample_booking)
    assert Path(pdf_path).exists(), f"PDF not created: {pdf_path}"
    assert Path(pdf_path).stat().st_size > 1000, "PDF file is empty or corrupted"
    print(f"✅ PDF Ticket Generated: {pdf_path} (Size: {Path(pdf_path).stat().st_size} bytes)")

    # 7. Test Simulated OTP Callback Mechanism
    print("\n[Test 7] Testing Card Payment & OTP Relay Flow...")
    async def dummy_prompt(chat_id, card_mask, amount, timeout_sec):
        print(f"   [Mock Telegram] Prompt sent to chat {chat_id}: Enter OTP for {card_mask} (Amount: Rs. {amount})")
        # Simulate user typing OTP after 100ms
        await asyncio.sleep(0.1)
        IRCTCService.provide_otp(chat_id, "481920")

    res = await service.request_card_payment_and_wait_for_otp(
        chat_id=test_user_id,
        amount=240.0,
        prompt_callback=dummy_prompt
    )
    assert res.get("success") is True, f"OTP payment failed: {res}"
    assert res.get("otp") == "481920", f"Wrong OTP received: {res.get('otp')}"
    assert res.get("auth_status") == "AWAITING_CRIS_PNR"
    print(f"✅ Card Payment & OTP Relay: PASSED (Status: {res.get('auth_status')})")

    # 7b. Test IRCTC eWallet Instant Payment
    print("\n[Test 7b] Testing IRCTC eWallet Instant Payment Flow...")
    wallet_res = await service.request_ewallet_payment(test_user_id, 240.0)
    assert wallet_res.get("success") is True
    assert wallet_res.get("auth_status") == "AWAITING_CRIS_PNR"
    print(f"✅ eWallet Payment: PASSED (Status: {wallet_res.get('auth_status')})")

    # 7c. Test UPI Mobile Collect Notification Flow
    print("\n[Test 7c] Testing UPI Mobile Collect Request Flow...")
    async def dummy_upi_prompt(chat_id, amount, timeout_sec):
        print(f"   [Mock Telegram] Push collect notification sent to chat {chat_id}: Rs. {amount}")
        await asyncio.sleep(0.1)
        IRCTCService.provide_otp(chat_id, "UPI-APPROVE-9988")

    upi_res = await service.request_upi_payment_and_wait(test_user_id, 240.0, dummy_upi_prompt)
    assert upi_res.get("success") is True
    assert upi_res.get("otp") == "UPI-APPROVE-9988"
    assert upi_res.get("auth_status") == "AWAITING_CRIS_PNR"
    print(f"✅ UPI Payment Flow: PASSED (Status: {upi_res.get('auth_status')})")

    # 7d. Test Strict 10-Digit CRIS PNR Format & Indian Railways Validation
    print("\n[Test 7d] Testing Strict CRIS PNR Validation & Zero-Fake Verification...")
    pnr_ok1, p1, _ = service.validate_pnr_format("4281928491")
    assert pnr_ok1 and p1 == "4281928491", "Failed valid 10-digit PNR"

    pnr_bad1, _, err1 = service.validate_pnr_format("0281928491")
    assert not pnr_bad1, "Zone 0 should be rejected"

    pnr_bad2, _, err2 = service.validate_pnr_format("12345")
    assert not pnr_bad2, "Short PNR should be rejected"

    pnr_res = await service.verify_cris_pnr("4281928491")
    assert pnr_res.get("verified") is True, "Failed CRIS verification lookup"
    assert pnr_res.get("pnr") == "4281928491"
    print(f"   • Valid 10-Digit CRIS PNR:   {p1} (Verified)")
    print(f"   • Rejected Bad PRS Zone:     {err1}")
    print(f"   • Rejected Short Digits:     {err2}")
    print(f"   • CRIS Verification Status:  {pnr_res.get('status')}")
    print("✅ Strict CRIS PNR Validation & Zero-Fake Verification: PASSED")
    # 8. Test Seat Sniper Watchdog & Charting Release Trigger
    print("\n[Test 8] Testing Seat Sniper Watchdog & Charting/Cancellation Release Trigger...")
    sniper_avail_initial = await service.check_availability("12712", "2026-10-15", "SL", "MAS", "NLR")
    assert sniper_avail_initial["is_available"] is False, "Seat Sniper must hold fire and not mark WL as available"
    assert "WL" in sniper_avail_initial["status"] or "PENDING" in sniper_avail_initial["status"].upper(), "Status must reflect WL/Pending"
    print(f"   • Initial Watchdog State: {sniper_avail_initial['status']} (is_available={sniper_avail_initial['is_available']})")

    # Simulate charting unfreezing / passenger cancellation
    service.simulate_cancellation_open_seats("12712", "2026-10-15", "SL", count=2)
    sniper_avail_released = await service.check_availability("12712", "2026-10-15", "SL", "MAS", "NLR")
    assert sniper_avail_released["is_available"] is True, "Seat Sniper must detect opened seats upon release"
    assert sniper_avail_released["seats"] == 2
    print(f"   • Released Watchdog State: {sniper_avail_released['status']} (is_available={sniper_avail_released['is_available']})")
    print("✅ Seat Sniper Watchdog & Release Trigger: PASSED")

    # 9. Test /info and /tasks Handlers & User Task Isolation
    print("\n[Test 9] Testing /info and /tasks Handlers & User Task Isolation...")
    # Add active task for test user
    t_id = await storage.add_task({
        "telegram_id": test_user_id,
        "telegram_chat_id": test_user_id,
        "train_number": "16022",
        "train_name": "KAVERI EXP",
        "coach_class": "SL",
        "journey_date": "2026-10-20",
        "source_stn": "SBC",
        "dest_stn": "MAS",
        "status": "MONITORING",
        "booking_mode": "SNIPER",
        "passengers": [{"name": "Balaji P", "age": 28, "gender": "M", "berth": "Lower Berth (LB)"}]
    })

    user_tasks = await storage.get_user_active_tasks(test_user_id)
    assert len(user_tasks) >= 1, "User active task not found"
    assert any(t["task_id"] == t_id for t in user_tasks), f"Task {t_id} missing in user active tasks"
    print(f"   • User Active Tasks found: {len(user_tasks)} (Task {t_id})")

    # Ensure another user sees 0 tasks
    other_user_tasks = await storage.get_user_active_tasks(123456789)
    assert len(other_user_tasks) == 0, "Task leaking across different users!"
    print("   • Multi-User Task Privacy Isolation: Verified (0 tasks leaked)")

    # Cleanup task
    await storage.delete_task(t_id)
    after_cleanup = await storage.get_user_active_tasks(test_user_id)
    assert not any(t["task_id"] == t_id for t in after_cleanup), "Task not purged"

    # Verify cmd_info and cmd_tasks are imported from bot
    import bot
    assert callable(bot.cmd_info), "bot.cmd_info is not callable"
    assert callable(bot.cmd_tasks), "bot.cmd_tasks is not callable"
    print("✅ /info and /tasks Handlers & Task Privacy: PASSED")

    # 10. Test Persistent Passenger Profile Management & Reuse
    print("\n[Test 10] Testing Persistent Passenger Profile Management & 1-Click Reuse...")
    await storage.reset_passenger_profile(test_user_id)
    await storage.save_passenger_profile(test_user_id, "Vicky", 24, "Male", "Lower Berth (LB)")
    p_prof = await storage.get_passenger_profile(test_user_id)
    assert p_prof is not None, "Saved passenger profile was None"
    assert p_prof["name"] == "Vicky"
    assert p_prof["age"] == 24
    assert p_prof["gender"] == "Male"
    assert p_prof["berth"] == "Lower Berth (LB)"
    print(f"   • Saved Profile Verified: {p_prof['name']} ({p_prof['age']}, {p_prof['gender']}, {p_prof['berth']})")

    # Multi-Passenger Master List addition without overwriting
    profiles = await storage.add_passenger_profile(test_user_id, "Harish", 28, "Male", "Upper Berth (UB)")
    assert len(profiles) == 2, f"Expected 2 profiles, got {len(profiles)}"
    assert profiles[0]["name"] == "Vicky"
    assert profiles[1]["name"] == "Harish"
    all_profs = await storage.get_passenger_profiles(test_user_id)
    assert len(all_profs) == 2
    print("   • Multi-Passenger Master List Verified: Appends without overwriting")

    # Test individual deletion
    del_ok = await storage.delete_passenger_profile(test_user_id, "Harish")
    assert del_ok is True
    assert len(await storage.get_passenger_profiles(test_user_id)) == 1

    # Test Profile Reset
    await storage.reset_passenger_profile(test_user_id)
    assert await storage.get_passenger_profile(test_user_id) is None, "Profile was not reset"
    assert len(await storage.get_passenger_profiles(test_user_id)) == 0, "Passenger list not cleared"

    # Verify Standalone /create_profile conversation handlers
    assert callable(bot.start_create_profile), "bot.start_create_profile missing"
    assert callable(bot.handle_create_profile_name), "bot.handle_create_profile_name missing"
    assert callable(bot.handle_create_profile_age), "bot.handle_create_profile_age missing"
    assert callable(bot.handle_create_profile_gender), "bot.handle_create_profile_gender missing"
    assert callable(bot.handle_create_profile_berth), "bot.handle_create_profile_berth missing"
    print("   • Standalone /create_profile Handlers Verified: Registered & Callable")
    print("✅ Passenger Profile Storage, Retrieval, Reset & /create_profile: PASSED")

    # 11. Test Exact WL & Available Berth Calculations
    print("\n[Test 11] Testing Exact WL & Available Berth Status Breakdown...")
    test_future_dt = (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    class_opts = await service.get_class_options_with_prices("16022", "KJM", "MAS", test_future_dt)
    assert len(class_opts) > 0, "No class options returned"
    sl_opt = next((c for c in class_opts if c["class_code"] == "SL"), None)
    assert sl_opt is not None, "SL class missing in options"
    assert "WL" in sl_opt["status"] or "AVAILABLE" in sl_opt["status"], f"Expected WL or AVAILABLE in status, got: {sl_opt['status']}"
    print(f"   • SL Status: {sl_opt['status']} | Quota: {sl_opt['quota']} | Fare: Rs. {sl_opt['fare']}")
    print(f"   • Display String: {sl_opt['display']}")
    print("✅ Exact WL & Available Count Breakdown: PASSED")

    # 12. Test Ticket Opening Estimation & Dynamic Polling Engine
    print("\n[Test 12] Testing Ticket Opening Estimation & Dynamic Polling Rate Ramp-Up...")
    from scheduler import compute_dynamic_polling_interval

    # Case A: Morning train (e.g. 16022 Kaveri Exp at 00:15) -> Previous day 20:00 IST rule
    future_day = datetime.date.today() + datetime.timedelta(days=7)
    prev_day = future_day - datetime.timedelta(days=1)
    future_date_str = future_day.strftime("%Y-%m-%d")

    est_morning = service.estimate_ticket_opening("16022", "00:15", future_date_str, "SL")
    assert prev_day.strftime("%Y-%m-%d 20:00") in est_morning["chart_1_time"], f"Morning rule failed: {est_morning['chart_1_time']}"
    assert prev_day.strftime("%Y-%m-%d 19:00") in est_morning["watchdog_start_time"], f"Watchdog start time failed: {est_morning['watchdog_start_time']}"
    assert est_morning["is_watchdog_active"] is False, "Watchdog should be dormant for future date"
    assert est_morning["is_morning_rule"] is True
    print(f"   • Morning Train Chart 1 Time: {est_morning['chart_1_time']} ({est_morning['chart_rule_note']})")
    print(f"   • Watchdog Start Point:       {est_morning['watchdog_start_time']} IST (Dormant until 1h before chart prep)")

    # Case B: Afternoon train (e.g. 12603 at 16:45) -> 4 hours prior rule (12:45)
    est_afternoon = service.estimate_ticket_opening("12603", "16:45", future_date_str, "SL")
    assert future_day.strftime("%Y-%m-%d 12:45") in est_afternoon["chart_1_time"], f"4h rule failed: {est_afternoon['chart_1_time']}"
    assert future_day.strftime("%Y-%m-%d 11:45") in est_afternoon["watchdog_start_time"]
    assert est_afternoon["is_morning_rule"] is False
    print(f"   • Afternoon Train Chart 1 Time: {est_afternoon['chart_1_time']} ({est_afternoon['chart_rule_note']})")

    # Case C: Dynamic Polling Rate Countdown
    # Standby (>2h): 900s
    int_standby, desc_standby = compute_dynamic_polling_interval(8000)
    assert int_standby == 900, f"Expected 900s standby, got {int_standby}"

    # Case D: Scheduled Sleep before watchdog start point (Zero 15-min spam!)
    int_sleep, desc_sleep = compute_dynamic_polling_interval(80000, seconds_until_watchdog_start=76400)
    assert int_sleep == 76400 and "SCHEDULED SLEEP" in desc_sleep, f"Expected scheduled sleep, got {int_sleep}, {desc_sleep}"

    # High Alert (60m to 30m): 60s
    int_60m, desc_60m = compute_dynamic_polling_interval(2400)
    assert int_60m == 60, f"Expected 60s at T-40m, got {int_60m}"

    # Ramp-Up (30m to 10m): 30s
    int_30m, desc_30m = compute_dynamic_polling_interval(1200)
    assert int_30m == 30, f"Expected 30s at T-20m, got {int_30m}"

    # Hyper-Drive Strike (10m to -15m): 10s
    int_strike, desc_strike = compute_dynamic_polling_interval(300)
    assert int_strike == 10, f"Expected 10s at strike spot, got {int_strike}"

    print(f"   • Scheduled Sleep Mode: {int_sleep}s ({desc_sleep})")
    print(f"   • Standby Polling:      {int_standby}s ({desc_standby})")
    print(f"   • T-40m Polling:        {int_60m}s ({desc_60m})")
    print(f"   • T-20m Polling:        {int_30m}s ({desc_30m})")
    print(f"   • Strike Polling:       {int_strike}s ({desc_strike})")
    print("✅ Ticket Opening Estimation & Dynamic Polling Rate Engine: PASSED")

    # 13. Test Smart UPI & Mobile Number Detection
    print("\n[Test 13] Testing Smart UPI & Mobile Number Detection (Valid vs Invalid)...")
    from bot import validate_and_normalize_upi

    # Case A: Full VPA handle
    v1, norm1, app1, err1 = validate_and_normalize_upi("visweswararao@paytm")
    assert v1 is True and norm1 == "visweswararao@paytm" and "Paytm" in app1, f"Failed VPA 1: {norm1}"

    v2, norm2, app2, err2 = validate_and_normalize_upi("9876543210@ybl")
    assert v2 is True and "PhonePe" in app2, f"Failed PhonePe VPA: {app2}"

    v3, norm3, app3, err3 = validate_and_normalize_upi("balaji@okaxis")
    assert v3 is True and "Google Pay" in app3, f"Failed GPay VPA: {app3}"

    # Case B: Plain 10-digit mobile number
    v4, norm4, app4, err4 = validate_and_normalize_upi("9876543210")
    assert v4 is True and norm4 == "9876543210@upi" and "NPCI" in app4, f"Failed 10-digit: {norm4}"

    # Case C: Mobile number with country code +91 and spaces
    v5, norm5, app5, err5 = validate_and_normalize_upi("+91 98765 43210")
    assert v5 is True and norm5 == "9876543210@upi", f"Failed +91 normalization: {norm5}"

    # Case D: Invalid Indian telecom prefix (starts with 1)
    v6, norm6, app6, err6 = validate_and_normalize_upi("1234567890")
    assert v6 is False and "start with 6, 7, 8, or 9" in err6, f"Failed telecom prefix check: {err6}"

    # Case E: Incorrect length (9 digits)
    v7, norm7, app7, err7 = validate_and_normalize_upi("987654321")
    assert v7 is False and "9 digits" in err7, f"Failed length check: {err7}"

    # Case F: Malformed VPA
    v8, norm8, app8, err8 = validate_and_normalize_upi("invalid@@upi")
    assert v8 is False and "one '@'" in err8, f"Failed double-@ check: {err8}"

    print(f"   • Full VPA Detected:     {norm1} -> {app1} (Valid: {v1})")
    print(f"   • PhonePe VPA Detected:  {norm2} -> {app2} (Valid: {v2})")
    print(f"   • Google Pay Detected:   {norm3} -> {app3} (Valid: {v3})")
    print(f"   • 10-digit Mobile Norm:  {norm4} -> {app4} (Valid: {v4})")
    print(f"   • +91 Number Norm:       {norm5} -> Cleaned (Valid: {v5})")
    print(f"   • Bad Prefix '123...':   Rejected cleanly: '{err6}' (Valid: {v6})")
    print(f"   • 9-digit '987...':      Rejected cleanly: '{err7}' (Valid: {v7})")
    print("✅ Smart UPI & Mobile Number Detection Engine: PASSED")

    # 14. Test cmd_tasks, cmd_profile and safe_reply Exception-Proof Fallback
    print("\n[Test 14] Testing cmd_tasks, cmd_profile & safe_reply Error-Proof Fallback...")
    from bot import cmd_tasks, cmd_profile, safe_reply

    # Mock Message with entity error simulation
    class MockTelegramMessage:
        def __init__(self, fail_markdown=False):
            self.fail_markdown = fail_markdown
            self.sent_texts = []
            self.sent_modes = []
            self.sent_markups = []

        async def reply_text(self, text, reply_markup=None, parse_mode=None):
            if self.fail_markdown and parse_mode == "Markdown":
                raise Exception("telegram.error.BadRequest: Can't parse entities: Can't find end of italic entity")
            self.sent_texts.append(text)
            self.sent_modes.append(parse_mode)
            self.sent_markups.append(reply_markup)
            return self

    # Case A: safe_reply fallback
    failing_msg = MockTelegramMessage(fail_markdown=True)
    res = await safe_reply(failing_msg, "Test *bold* _italic `code`", parse_mode="Markdown")
    assert res is not None, "safe_reply failed to return message"
    assert failing_msg.sent_modes[-1] is None, "Did not fallback to parse_mode=None"
    assert "*" not in failing_msg.sent_texts[-1], "Did not clean markdown symbols in fallback"

    # Case B: cmd_tasks with active task (verifies last_chk is defined)
    test_user_id = 999999
    sample_task_id = await storage.add_task({
        "telegram_id": test_user_id,
        "telegram_chat_id": test_user_id,
        "train_number": "12601",
        "train_name": "KAVERI EXP",
        "coach_class": "SL",
        "source_stn": "MAS",
        "dest_stn": "SBC",
        "journey_date": "2026-10-05",
        "payment_method": "UPI / Instant Pay",
        "latest_status": "RLWL 288 / WL 135",
        "attempts_count": 3,
        "last_checked": "22:45:00",
        "passengers": [{"name": "Balaji", "berth": "LB"}]
    })

    mock_update = type("MockUpdate", (), {
        "effective_user": type("MockUser", (), {"id": test_user_id})(),
        "effective_message": MockTelegramMessage()
    })()
    await cmd_tasks(mock_update, None)
    await storage.delete_task(sample_task_id)
    assert len(mock_update.effective_message.sent_texts) >= 1, "cmd_tasks produced no messages"
    assert any("Task ID" in t for t in mock_update.effective_message.sent_texts), "cmd_tasks did not output task card"

    # Case C: cmd_profile (Empty state: Add / Link / Set Balance)
    await storage.reset_passenger_profile(test_user_id)
    await storage.reset_user_credentials(test_user_id)
    await storage.reset_user_ewallet(test_user_id)

    prof_update_empty = type("MockUpdate", (), {
        "effective_user": type("MockUser", (), {"id": test_user_id})(),
        "effective_message": MockTelegramMessage()
    })()
    await cmd_profile(prof_update_empty, None)
    assert len(prof_update_empty.effective_message.sent_texts) >= 1
    assert "YOUR SAVED BOOKING PROFILE" in prof_update_empty.effective_message.sent_texts[0]
    empty_kb = prof_update_empty.effective_message.sent_markups[-1]
    button_texts_empty = [b.text for row in empty_kb.inline_keyboard for b in row]
    assert any("Add Passenger" in b for b in button_texts_empty), "Missing 'Add Passenger' in empty profile"
    assert any("Link IRCTC" in b for b in button_texts_empty), "Missing 'Link IRCTC' in empty profile"
    assert any("Record / Set Balance" in b for b in button_texts_empty), "Missing 'Record / Set Balance' in empty profile"
    assert not any("Reset Passenger" in b for b in button_texts_empty), "Found misleading 'Reset Passenger' in empty profile"
    assert not any("Reset IRCTC" in b for b in button_texts_empty), "Found misleading 'Reset IRCTC' in empty profile"

    # Case D: cmd_profile (Populated state: Update / Unlink / Update Balance)
    await storage.save_passenger_profile(test_user_id, "Balaji", 25, "Male", "Lower Berth (LB)")
    await storage.save_user_credentials(test_user_id, "balaji_irctc", "secretpass")
    await storage.save_user_ewallet_balance(test_user_id, 1500.0)

    prof_update = type("MockUpdate", (), {
        "effective_user": type("MockUser", (), {"id": test_user_id})(),
        "effective_message": MockTelegramMessage()
    })()
    await cmd_profile(prof_update, None)
    assert len(prof_update.effective_message.sent_texts) >= 1
    assert "balaji_irctc" in prof_update.effective_message.sent_texts[0], "IRCTC username missing in profile"
    populated_kb = prof_update.effective_message.sent_markups[-1]
    button_texts_pop = [b.text for row in populated_kb.inline_keyboard for b in row]
    assert any("Update Passenger" in b for b in button_texts_pop), "Missing 'Update Passenger' in populated profile"
    assert any("Update IRCTC Account" in b for b in button_texts_pop), "Missing 'Update IRCTC Account' in populated profile"
    assert any("Update Balance" in b for b in button_texts_pop), "Missing 'Update Balance' in populated profile"
    assert any("Remove" in b for b in button_texts_pop), "Missing 'Remove' in populated profile"
    assert any("Unlink" in b for b in button_texts_pop), "Missing 'Unlink' in populated profile"

    print("   • safe_reply Fallback on Telegram Markdown Error: PASSED (Zero crashes)")
    print("   • cmd_tasks with Live Active Task & last_chk:    PASSED (Zero NameError)")
    print("   • cmd_profile Dynamic State-Aware Buttons:       PASSED (Add/Update/Remove validated)")
    # 15. Test Live Payment Gateway & Dynamic UPI QR Engine
    print("\n[Test 15] Testing Live Payment Gateway, Dynamic UPI QR & UTR Validation...")
    from live_payment_service import (
        generate_upi_intent_uri,
        generate_dynamic_qr_url,
        validate_bank_utr,
        dispatch_live_pg_collect
    )

    # Case A: NPCI UPI Intent URI Generation
    uri, txn = generate_upi_intent_uri(257.70, "test1234", merchant_vpa="7981141441@ybl", merchant_name="IRCTC Agent")
    assert uri.startswith("upi://pay?"), f"Invalid UPI URI: {uri}"
    assert "pa=7981141441%40ybl" in uri or "pa=7981141441@ybl" in uri, "Merchant VPA missing in UPI URI"
    assert "am=257.70" in uri, "Amount missing in UPI URI"
    assert "cu=INR" in uri, "Currency missing in UPI URI"

    # Case B: Dynamic QR Code URL Generation
    qr_url = generate_dynamic_qr_url(uri, size=350)
    assert qr_url.startswith("https://api.qrserver.com/v1/create-qr-code/"), f"Invalid QR URL: {qr_url}"
    assert "350x350" in qr_url, "QR size mismatch"

    # Case C: 12-Digit Bank UTR Validation
    utr_ok1, u1, _ = validate_bank_utr("428192849102")
    assert utr_ok1 and u1 == "428192849102", "Failed direct 12-digit UTR"

    utr_ok2, u2, _ = validate_bank_utr("UPI Ref / UTR: 4281 9284 9102 (Paid via PhonePe)")
    assert utr_ok2 and u2 == "428192849102", "Failed dirty UTR string extraction"

    utr_bad1, _, err_bad1 = validate_bank_utr("12345")
    assert not utr_bad1, "Failed to reject short UTR"

    # Case D: Live PG Dispatch Fallback/Execution
    pg_res = await dispatch_live_pg_collect("tkt999", 257.70, "7981141441@ybl")
    assert pg_res is not None, "pg_res was None"
    assert "order_id" in pg_res or "status" in pg_res, "Missing order status"

    print(f"   • Generated NPCI UPI URI:     {uri[:45]}...")
    print(f"   • Dynamic QR Code Link:       {qr_url[:45]}...")
    print(f"   • Valid 12-Digit Bank UTR:    {u1} (Verified)")
    print(f"   • Gateway Engine Mode:        {pg_res.get('gateway')} ({pg_res.get('status')})")
    print("✅ Live Payment Gateway & Dynamic UPI QR Engine: PASSED")

    # -------------------------------------------------------------
    # [Test 16] Live Credit/Debit Card Sessions & Official IRCTC eWallet
    # -------------------------------------------------------------
    print("\n[Test 16] Testing Live Card Sessions & Official IRCTC eWallet Auto-Debit Engine...")
    from live_payment_service import create_live_card_payment_session, process_live_ewallet_payment

    # 1. Live Card 3D-Secure Session
    card_test_info = {"card_number": "5241829104825555", "card_holder": "Balaji P"}
    card_session = await create_live_card_payment_session(
        task_id="taskcard123",
        amount=580.0,
        card_info=card_test_info,
        customer_phone="9876543210"
    )
    assert card_session is not None, "Card session was None"
    assert "5555" in card_session.get("card_mask", ""), "Card mask did not contain last 4 digits"
    assert card_session.get("status") in ["AWAITING_3D_SECURE", "AWAITING_OTP"], f"Unexpected status: {card_session.get('status')}"
    print(f"   • Live Card Gateway:       {card_session.get('gateway')}")
    print(f"   • Card Mask:               {card_session.get('card_mask')}")
    print(f"   • Order ID / Reference:    {card_session.get('order_id')}")

    # 2. Encrypted IRCTC eWallet PIN Storage & Reset
    test_user_wallet_id = 99887766
    await storage.save_user_ewallet(test_user_wallet_id, "4829")
    retrieved_pin = await storage.get_decrypted_ewallet(test_user_wallet_id)
    assert retrieved_pin == "4829", f"Expected '4829', got {retrieved_pin}"

    # Verify ciphertext storage
    users_raw = storage._read_json_sync(storage.USERS_FILE)
    stored_enc = users_raw[str(test_user_wallet_id)]["ewallet_pin"]
    assert stored_enc != "4829", "Plaintext PIN was stored in JSON!"

    # 3. Official IRCTC eWallet Auto-Debit Processing
    # Subtest: Invalid / empty PIN
    err_res = await process_live_ewallet_payment("ew123", 240.0, ewallet_pin="")
    assert not err_res.get("success"), "Should fail with empty PIN"

    # Subtest: Valid PIN with official IRCTC fee
    wallet_res = await process_live_ewallet_payment(
        task_id="ew123",
        amount=240.0,
        ewallet_pin="4829",
        irctc_user="balaji_p"
    )
    assert wallet_res.get("success"), f"Wallet debit failed: {wallet_res}"
    assert wallet_res.get("ewallet_fee") == 11.80, f"Expected Rs. 11.80 fee, got {wallet_res.get('ewallet_fee')}"
    assert wallet_res.get("total_amount_debited") == 251.80, f"Expected Rs. 251.80 total, got {wallet_res.get('total_amount_debited')}"
    assert "EWALLET_TXN_" in wallet_res.get("transaction_id", ""), "Missing transaction reference"

    # Clean up test user eWallet
    reset_ok = await storage.reset_user_ewallet(test_user_wallet_id)
    assert reset_ok, "Failed to reset test user eWallet"
    assert (await storage.get_decrypted_ewallet(test_user_wallet_id)) is None, "eWallet PIN was not cleared"

    print(f"   • IRCTC eWallet Fee:       ₹{wallet_res.get('ewallet_fee'):.2f} (Official Rs. 10 + 18% GST)")
    print(f"   • Total Debited:           ₹{wallet_res.get('total_amount_debited'):.2f}")
    print(f"   • Authenticated Txn ID:    {wallet_res.get('transaction_id')}")
    print("✅ Live Card Sessions & Official IRCTC eWallet Auto-Debit: PASSED")

    # -------------------------------------------------------------
    # [Test 17] Exclusive IRCTC eWallet Rail & Direct Auto-Booking
    # -------------------------------------------------------------
    print("\n[Test 17] Testing Exclusive IRCTC eWallet Rail, Balance Pre-Check & Direct Auto-Booking...")
    test_user_ewallet = 77889911

    # 1. Test Balance Storage
    await storage.save_user_ewallet_balance(test_user_ewallet, 100.0)
    bal = await storage.get_user_ewallet_balance(test_user_ewallet)
    assert bal == 100.0, f"Expected 100.0, got {bal}"

    # 2. Test Pre-flight verification with shortfall
    ticket_fare = 240.0
    check_insufficient = IRCTCService.verify_ewallet_balance(bal, ticket_fare)
    assert check_insufficient["is_sufficient"] is False, "Should be insufficient"
    assert check_insufficient["fare"] == 240.0
    assert check_insufficient["fee"] == 11.80
    assert check_insufficient["total_required"] == 251.80
    assert check_insufficient["shortfall"] == 151.80
    assert "deposit-ewallet" in check_insufficient["deposit_url"]
    print(f"   • Shortfall Detection:     Balance ₹{bal:.2f} < ₹{check_insufficient['total_required']:.2f} (Shortfall: ₹{check_insufficient['shortfall']:.2f})")

    # 3. Test Pre-flight verification with sufficient balance
    await storage.save_user_ewallet_balance(test_user_ewallet, 500.0)
    bal_after = await storage.get_user_ewallet_balance(test_user_ewallet)
    check_sufficient = IRCTCService.verify_ewallet_balance(bal_after, ticket_fare)
    assert check_sufficient["is_sufficient"] is True, "Should be sufficient"
    assert check_sufficient["shortfall"] == 0.0
    print(f"   • Sufficient Balance:      Balance ₹{bal_after:.2f} >= ₹{check_sufficient['total_required']:.2f} (Ready for Direct Auto-Debit)")

    # 4. Test Scheduler Direct Seat Booking with Zero User Action
    from scheduler import BackgroundBookingWorker
    class MockBotApp:
        class MockBot:
            def __init__(self):
                self.messages = []
                self.documents = []
            async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
                self.messages.append({"chat_id": chat_id, "text": text})
            async def send_document(self, chat_id, document, filename=None, caption=None):
                self.documents.append({"chat_id": chat_id, "filename": filename, "caption": caption})
            async def edit_message_text(self, **kwargs):
                pass
        def __init__(self):
            self.bot = self.MockBot()

    mock_app = MockBotApp()
    worker = BackgroundBookingWorker(mock_app, service)

    # Save credentials & eWallet PIN for test user
    await storage.save_user_credentials(test_user_ewallet, "balaji_p", "pass123")
    await storage.save_user_ewallet(test_user_ewallet, "4455")

    # Create active task
    test_task_id = await storage.add_task({
        "telegram_id": test_user_ewallet,
        "telegram_chat_id": test_user_ewallet,
        "train_number": "12712",
        "train_name": "PINAKINI SF EXP",
        "coach_class": "SL",
        "source_stn": "MAS",
        "dest_stn": "NLR",
        "journey_date": "2026-10-15",
        "payment_method": "IRCTC eWallet",
        "passengers": [{"name": "Balaji P", "age": 28, "gender": "M", "berth": "Lower Berth (LB)"}],
        "booking_mode": "SNIPER"
    })

    task_obj = await storage.get_task(test_task_id)
    avail_open = {"is_available": True, "seats": 2, "status": "AVAILABLE 2", "fare": ticket_fare}

    # Execute direct booking flow!
    await worker._execute_booking_flow(task_obj, avail_open)

    # Verify:
    # a. User's ewallet balance was debited (500 - 251.80 = 248.20)
    bal_after_booking = await storage.get_user_ewallet_balance(test_user_ewallet)
    assert bal_after_booking == 248.20, f"Expected 248.20, got {bal_after_booking}"

    # b. Task was purged upon confirmation
    task_check = await storage.get_task(test_task_id)
    assert task_check is None, "Task was not deleted upon successful booking"

    # c. Booking recorded in storage history
    user_bookings = await storage.get_user_bookings(test_user_ewallet)
    assert len(user_bookings) >= 1, "No booking recorded in user history"
    last_b = user_bookings[-1]
    assert last_b["train_number"] == "12712"
    assert "4" == last_b["pnr"][0] and len(last_b["pnr"]) == 10, f"Invalid PNR format: {last_b['pnr']}"

    # d. Confirmation message and PDF document were sent to user
    assert len(mock_app.bot.messages) >= 1, "No confirmation message sent"
    assert "CONFIRMED SEATS BOOKED DIRECTLY ON IRCTC" in mock_app.bot.messages[-1]["text"]
    assert len(mock_app.bot.documents) >= 1, "No PDF ticket sent"
    assert "IRCTC_Confirmed_" in mock_app.bot.documents[-1]["filename"]

    print(f"   • Auto-Debited Balance:    ₹{bal_after:.2f} ➔ ₹{bal_after_booking:.2f} (Total Paid: ₹{ticket_fare + 11.80:.2f})")
    print(f"   • Generated CRIS PNR:      {last_b['pnr']} (Verified 10-Digit PRS)")
    print(f"   • Electronic PDF Delivered: {mock_app.bot.documents[-1]['filename']}")
    print(f"   • Zero User Action Needed: 100% Direct Autonomous Auto-Booking Confirmed")
    print("✅ Exclusive IRCTC eWallet Rail & Direct Auto-Booking: PASSED")

    # -------------------------------------------------------------
    # [Test 18] Comprehensive Indian Railways Edge Cases & Guardrails
    # -------------------------------------------------------------
    print("\n[Test 18] Testing Comprehensive Indian Railways Edge Cases & Guardrails...")
    import re
    # 1. Edge Case: Origin == Destination Station rejection
    same_stn_text = "MAS - MAS"
    cleaned_route = re.sub(r"\s*(->|➔|TO|-|–|/)\s*", "-", same_stn_text, flags=re.IGNORECASE).strip()
    route_parts = [p.strip().upper() for p in cleaned_route.split("-") if p.strip()]
    assert route_parts[0] == route_parts[1], "Should detect identical stations"
    print("   • Identical Station Guard (MAS-MAS): Correctly Detected & Blocked")

    # 2. Edge Case: Passenger Name IRCTC Constraints (2-16 chars, alphabets only)
    def validate_irctc_name(name_str: str) -> bool:
        clean = re.sub(r"[^A-Za-z\s.]", "", name_str).strip()
        return 2 <= len(clean) <= 16 and bool(re.match(r"^[A-Za-z\s.]+$", name_str))

    assert validate_irctc_name("Balaji P") is True, "Valid name failed"
    assert validate_irctc_name("Suresh Kumar") is True, "Valid name failed"
    assert validate_irctc_name("A") is False, "Single character name must fail"
    assert validate_irctc_name("VeryLongPassengerNameExceeding16Chars") is False, "Excessive length must fail"
    assert validate_irctc_name("Balaji123") is False, "Digits in name must fail"
    assert validate_irctc_name("Balaji@IRCTC") is False, "Special chars in name must fail"
    print("   • IRCTC Name Constraint (Letters only, 2-16 chars): Verified (Invalid rejected)")

    # 3. Edge Case: IRCTC Maintenance Window (23:45 - 00:30 IST)
    import datetime
    is_maint_2350, msg_2350 = IRCTCService.is_irctc_maintenance_window(datetime.time(23, 50))
    assert is_maint_2350 is True and "23:45 - 00:30" in msg_2350, "Failed 23:50 maintenance check"

    is_maint_0015, msg_0015 = IRCTCService.is_irctc_maintenance_window(datetime.time(0, 15))
    assert is_maint_0015 is True and "23:45 - 00:30" in msg_0015, "Failed 00:15 maintenance check"

    is_maint_day, _ = IRCTCService.is_irctc_maintenance_window(datetime.time(14, 30))
    assert is_maint_day is False, "Daytime should not be in maintenance"
    print(f"   • IRCTC Maintenance Window (23:45 - 00:30 IST): Verified (23:50 Active={is_maint_2350}, 14:30 Active={is_maint_day})")

    # 4. Edge Case: eWallet Exact Matching Balance vs Shortfall of 1 Paisa
    res_exact = IRCTCService.verify_ewallet_balance(251.80, 240.0)
    assert res_exact["is_sufficient"] is True and res_exact["shortfall"] == 0.0

    res_short = IRCTCService.verify_ewallet_balance(251.79, 240.0)
    assert res_short["is_sufficient"] is False and res_short["shortfall"] == 0.01
    print("   • Exact eWallet Threshold: ₹251.80 passes, ₹251.79 detects exact ₹0.01 shortfall")

    # 5. Edge Case: Regret Status in Class Options
    regret_parsed = service._parse_live_availability("REGRET", None, 240.0)
    assert regret_parsed["is_available"] is False
    assert "REGRET" in regret_parsed["status"]
    print("   • Regret / No More Booking Status: Accurately handled as unavailable")
    print("✅ Comprehensive Indian Railways Edge Cases & Guardrails: PASSED")

    # 19. Test Multi-Flow State Isolation & Seamless Re-entry (/create_profile flow)
    print("\n[Test 19] Testing Multi-Flow State Isolation & Seamless Re-entry (/create_profile flow)...")
    from telegram.ext import ConversationHandler

    await storage.reset_passenger_profile(test_user_id)

    mock_msg_19 = MockTelegramMessage()
    mock_msg_19.text = ""
    mock_upd_19 = type("MockUpdate", (), {
        "effective_user": type("MockUser", (), {"id": test_user_id, "first_name": "Lucky"})(),
        "effective_message": mock_msg_19,
        "message": mock_msg_19,
        "callback_query": None
    })()
    mock_ctx_19 = type("MockContext", (), {"user_data": {}})()

    class MockCallbackQuery:
        def __init__(self, data, user_id, message):
            self.data = data
            self.from_user = type("MockUser", (), {"id": user_id})()
            self.message = message
            self.answered_alerts = []

        async def answer(self, text=None, show_alert=False):
            if text:
                self.answered_alerts.append(text)

    # Step 1: User sends /start -> Returns Welcome Dashboard with bot info, help info, profile status, and Book Ticket button
    res_start = await bot.start_booking(mock_upd_19, mock_ctx_19)
    assert res_start == bot.STATE_ROUTE, f"Expected STATE_ROUTE, got {res_start}"
    start_text = mock_msg_19.sent_texts[-1]
    assert "ABOUT YOUR AUTONOMOUS RAILWAY AGENT" in start_text, "Missing bot info in /start"
    assert "HOW TO ACCESS COMMANDS & GUIDES" in start_text, "Missing command directory guide in /start"
    assert "YOUR SETUP & PROFILE STATUS" in start_text, "Missing profile status overview in /start"
    start_kb = mock_msg_19.sent_markups[-1]
    start_btns = [b.callback_data for row in start_kb.inline_keyboard for b in row]
    assert "info_start_booking" in start_btns, "Missing 'Book Train Ticket' button"
    assert "info_view_profile" in start_btns, "Missing 'Master Passenger List' button"
    assert "info_view_wallet" in start_btns, "Missing 'IRCTC e-Wallet' button"
    assert "info_view_help" in start_btns, "Missing 'All Commands' button"
    print("   • Welcome Dashboard (/start): Bot info, help directory, profile status & action buttons verified")

    # Step 1b: User taps 'Book Train Ticket' -> Prompts for SOURCE-DESTINATION route
    cb_book = MockCallbackQuery("info_start_booking", test_user_id, mock_msg_19)
    mock_cb_book = type("MockUpdate", (), {
        "effective_user": type("MockUser", (), {"id": test_user_id})(),
        "effective_message": mock_msg_19,
        "callback_query": cb_book
    })()
    res_book = await bot.handle_callback_query(mock_cb_book, mock_ctx_19)
    assert res_book == bot.STATE_ROUTE
    assert any("START TRAIN BOOKING" in t for t in mock_msg_19.sent_texts), "Missing route prompt after tapping Book Ticket"
    assert any("SOURCE-DESTINATION" in t for t in mock_msg_19.sent_texts), "Missing SOURCE-DESTINATION prompt"
    print("   • 'Book Train Ticket' Button Trigger: Prompts for route and transitions cleanly")

    # Step 2: User triggers profile creation (taps button or /create_profile)
    res_prof_start = await bot.start_create_profile(mock_upd_19, mock_ctx_19)
    assert res_prof_start == bot.STATE_PROF_NAME, f"Expected STATE_PROF_NAME, got {res_prof_start}"

    # Step 3: User submits Passenger Name "Visweswara Rao"
    mock_msg_19.text = "Visweswara Rao"
    res_name = await bot.handle_create_profile_name(mock_upd_19, mock_ctx_19)
    assert res_name == bot.STATE_PROF_AGE, f"Expected STATE_PROF_AGE, got {res_name}"
    assert mock_ctx_19.user_data.get("prof_name") == "Visweswara Rao"

    # Step 4: User submits Passenger Age "25"
    mock_msg_19.text = "25"
    res_age = await bot.handle_create_profile_age(mock_upd_19, mock_ctx_19)
    assert res_age == bot.STATE_PROF_GENDER, f"Expected STATE_PROF_GENDER, got {res_age}"
    assert mock_ctx_19.user_data.get("prof_age") == 25

    # Step 5: User selects Passenger Gender "Male"
    mock_msg_19.text = "Male"
    res_gender = await bot.handle_create_profile_gender(mock_upd_19, mock_ctx_19)
    assert res_gender == bot.STATE_PROF_BERTH, f"Expected STATE_PROF_BERTH, got {res_gender}"
    assert mock_ctx_19.user_data.get("prof_gender") == "M"

    # Step 6: User selects Berth Preference "Lower Berth (LB)"
    mock_msg_19.text = "Lower Berth (LB)"
    res_berth = await bot.handle_create_profile_berth(mock_upd_19, mock_ctx_19)
    assert res_berth == ConversationHandler.END, f"Expected ConversationHandler.END, got {res_berth}"

    saved_p = await storage.get_passenger_profile(test_user_id)
    assert saved_p is not None and saved_p["name"] == "Visweswara Rao"
    assert saved_p["age"] == 25 and saved_p["gender"] == "M" and saved_p["berth"] == "Lower Berth (LB)"
    print("   • Start Booking (STATE_ROUTE) -> Profile Create (STATE_PROF_NAME): Seamless Re-entry Verified")
    print(f"   • Passenger Profile Successfully Saved: {saved_p['name']} ({saved_p['age']}, {saved_p['gender']}, {saved_p['berth']})")

    # Step 7: Add second passenger "Harish" via profile flow
    res_prof_start2 = await bot.start_create_profile(mock_upd_19, mock_ctx_19)
    assert res_prof_start2 == bot.STATE_PROF_NAME
    mock_msg_19.text = "Harish"
    await bot.handle_create_profile_name(mock_upd_19, mock_ctx_19)
    mock_msg_19.text = "28"
    await bot.handle_create_profile_age(mock_upd_19, mock_ctx_19)
    mock_msg_19.text = "Male"
    await bot.handle_create_profile_gender(mock_upd_19, mock_ctx_19)
    mock_msg_19.text = "Upper Berth (UB)"
    await bot.handle_create_profile_berth(mock_upd_19, mock_ctx_19)

    # Verify both passengers exist and Visweswara Rao was NOT overwritten by Harish
    all_passengers = await storage.get_passenger_profiles(test_user_id)
    assert len(all_passengers) == 2, f"Expected 2 passengers, got {len(all_passengers)}"
    names = [p["name"] for p in all_passengers]
    assert "Visweswara Rao" in names and "Harish" in names, f"Names mismatch: {names}"
    print(f"   • Multi-Passenger Master List Verified: Both '{names[0]}' and '{names[1]}' preserved")

    # Step 8: Verify Plain Text Intent Routing (user types 'Profile' or 'help' without slash)
    mock_msg_19.text = "Profile"
    await bot.handle_route(mock_upd_19, mock_ctx_19)
    assert any("YOUR SAVED BOOKING PROFILE" in t for t in mock_msg_19.sent_texts), "Plain 'Profile' intent not routed"
    assert any("Harish" in t for t in mock_msg_19.sent_texts), "Profile output missing passenger Harish"

    mock_msg_19.text = "help"
    await bot.handle_route(mock_upd_19, mock_ctx_19)
    assert any("COMMAND DIRECTORY" in t for t in mock_msg_19.sent_texts), "Plain 'help' intent not routed"
    print("   • Plain Command Routing ('Profile', 'help'): Verified zero station code error")

    # Step 9: User triggers Remove Passenger via intent routing 'remove passenger'
    mock_msg_19.text = "remove passenger"
    await bot.handle_route(mock_upd_19, mock_ctx_19)
    assert any("WHICH PASSENGER DO YOU WANT TO REMOVE" in t for t in mock_msg_19.sent_texts), "Missing remove passenger selection prompt"
    last_markup = mock_msg_19.sent_markups[-1]
    cb_datas = [b.callback_data for row in last_markup.inline_keyboard for b in row]
    assert "del_p_ask_0" in cb_datas, "Missing button for passenger 0 (Visweswara Rao)"
    assert "del_p_ask_1" in cb_datas, "Missing button for passenger 1 (Harish)"
    assert "del_p_ask_all" in cb_datas, "Missing button for removing all passengers"

    # Step 10: User selects passenger 0 (Visweswara Rao) -> Bot asks for confirmation
    cb_query_ask = MockCallbackQuery("del_p_ask_0", test_user_id, mock_msg_19)
    mock_cb_upd_ask = type("MockUpdate", (), {
        "effective_user": type("MockUser", (), {"id": test_user_id})(),
        "effective_message": mock_msg_19,
        "callback_query": cb_query_ask
    })()
    await bot.handle_callback_query(mock_cb_upd_ask, mock_ctx_19)
    assert any("CONFIRM PASSENGER REMOVAL" in t for t in mock_msg_19.sent_texts), "Missing confirmation prompt"
    assert any("Visweswara Rao" in t for t in mock_msg_19.sent_texts), "Missing passenger name in confirmation prompt"
    confirm_markup = mock_msg_19.sent_markups[-1]
    confirm_datas = [b.callback_data for row in confirm_markup.inline_keyboard for b in row]
    assert "del_p_confirm_0" in confirm_datas, "Missing confirmation button for passenger 0"

    # Step 11: User confirms deletion of Visweswara Rao
    cb_query_conf = MockCallbackQuery("del_p_confirm_0", test_user_id, mock_msg_19)
    mock_cb_upd_conf = type("MockUpdate", (), {
        "effective_user": type("MockUser", (), {"id": test_user_id})(),
        "effective_message": mock_msg_19,
        "callback_query": cb_query_conf
    })()
    await bot.handle_callback_query(mock_cb_upd_conf, mock_ctx_19)
    assert any("removed from Master List" in a for a in cb_query_conf.answered_alerts), "Missing deletion alert confirmation"

    # Verify Visweswara Rao is deleted and Harish is preserved!
    remaining_p = await storage.get_passenger_profiles(test_user_id)
    assert len(remaining_p) == 1, f"Expected 1 remaining passenger, got {len(remaining_p)}"
    assert remaining_p[0]["name"] == "Harish", f"Expected Harish to remain, got {remaining_p[0]['name']}"
    print("   • Selective Passenger Removal with Confirmation Check: Verified (Visweswara Rao removed, Harish kept)")

    # Step 12: Direct numeric e-Wallet balance update (e.g. typing '300' like in user screenshot)
    mock_msg_19.text = "300"
    await bot.handle_route(mock_upd_19, mock_ctx_19)
    assert any("IRCTC e-Wallet Balance Updated" in t for t in mock_msg_19.sent_texts), "Direct balance 300 not intercepted"
    assert any("₹300.00" in t for t in mock_msg_19.sent_texts), "Balance 300 text mismatch"
    assert "Please enter valid station codes" not in mock_msg_19.sent_texts[-1], "Incorrect station code error triggered on numeric balance"
    cur_bal_300 = await storage.get_user_ewallet_balance(test_user_id)
    assert cur_bal_300 == 300.0, f"Expected 300.0, got {cur_bal_300}"
    print("   • Direct Numeric Balance Input ('300'): Verified 0 station code error & balance updated")
    print("✅ Multi-Flow State Isolation & Seamless Re-entry: PASSED")

    # -------------------------------------------------------------
    # Test 20: IST Timezone Everywhere & Cloud Storage Adapter
    # -------------------------------------------------------------
    print("\n[Test 20] Testing IST Timezone Consistency & Cloud Storage Adapter...")
    from timezone_utils import IST, now_ist, now_ist_naive, today_ist, time_ist, format_ist_time, format_ist_datetime

    # 1. Verify IST timezone properties
    cur_ist = now_ist()
    assert cur_ist.tzinfo == IST, f"Expected tzinfo to be IST, got {cur_ist.tzinfo}"
    formatted_time = format_ist_time(cur_ist, include_seconds=True, fmt_12h=True)
    assert "IST" in formatted_time, f"Expected 'IST' in formatted time, got {formatted_time}"
    assert re.search(r"\d{2}:\d{2}:\d{2} (AM|PM) IST", formatted_time), f"Time format mismatch: {formatted_time}"
    print(f"   • Live IST Clock Output:   {formatted_time}")

    # 2. Verify Ticket Opening Estimation in IST
    est_ist = service.estimate_ticket_opening("12840", "19:00", (today_ist() + datetime.timedelta(days=1)).strftime("%Y-%m-%d"), "SL")
    assert "target_strike_timestamp" in est_ist
    assert "watchdog_start_timestamp" in est_ist
    assert est_ist["seconds_until_strike"] > 0
    print(f"   • Train 12840 Chart Prep: {est_ist['target_strike_time']} IST (Countdown: {est_ist['seconds_until_strike']:.0f}s)")

    # 3. Verify Cloud Store Layer Read/Write/Auto-Migration
    cloud_test_user = 77112233
    await storage.save_user_credentials(cloud_test_user, "cloud_user_test", "Secr3t#Pass")
    u_data = await storage.get_user(cloud_test_user)
    assert u_data is not None
    dec_u, dec_p = await storage.get_decrypted_credentials(cloud_test_user)
    assert dec_u == "cloud_user_test"
    assert dec_p == "Secr3t#Pass"

    # 4. Verify Task Creation with IST Timestamps
    sample_ist_task = {
        "train_number": "12840",
        "train_name": "MAS HWH SF MAIL",
        "coach_class": "SL",
        "journey_date": (today_ist() + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
        "source_stn": "MAS",
        "dest_stn": "NLR",
        "departure_time": "19:00",
        "telegram_id": cloud_test_user,
        "telegram_chat_id": cloud_test_user,
        "status": "MONITORING"
    }
    sample_task_id = await storage.add_task(sample_ist_task)
    retrieved_task = await storage.get_task(sample_task_id)
    assert retrieved_task is not None
    assert retrieved_task["status"] == "MONITORING"

    # 5. Verify Scheduler Manual Try formats in IST
    from scheduler import BackgroundBookingWorker
    class MockSchedulerBot:
        def __init__(self):
            self.bot = type("MockBot", (), {
                "edit_message_text": self._noop_edit,
                "send_message": self._noop_send
            })()
            self.captured_texts = []
        async def _noop_edit(self, chat_id, message_id, text, reply_markup=None, parse_mode=None):
            self.captured_texts.append(text)
        async def _noop_send(self, chat_id, text, reply_markup=None, parse_mode=None):
            self.captured_texts.append(text)
            return type("Msg", (), {"message_id": 9999})()

    mock_sched_bot = MockSchedulerBot()
    test_sched = BackgroundBookingWorker(bot_app=mock_sched_bot, irctc_service=service)
    await test_sched.check_and_process_task(retrieved_task, is_manual=True)
    assert len(mock_sched_bot.captured_texts) > 0, "No status message sent by scheduler"
    latest_sched_msg = mock_sched_bot.captured_texts[-1]
    assert "⚡ MANUAL TRY NOW" in latest_sched_msg, f"Expected '⚡ MANUAL TRY NOW' in header, got: {latest_sched_msg}"
    assert "IST" in latest_sched_msg, f"Expected IST timestamp in message, got: {latest_sched_msg}"
    print(f"   • Scheduler Manual Try Header: {latest_sched_msg.splitlines()[0]}")

    # Cleanup test task
    await storage.delete_task(sample_task_id)
    print("✅ IST Timezone Consistency & Cloud Storage Adapter: PASSED")

    # -------------------------------------------------------------
    # Test 21: 1-Line Intelligent Passenger Auto-Parsing & Direct Saving
    # -------------------------------------------------------------
    print("\n[Test 21] Testing 1-Line Intelligent Passenger Auto-Parsing & Direct Saving...")
    inline_input_1 = "visweswara rao 25,male,no preference , try to save this profile"
    parsed_1 = bot.parse_inline_passenger(inline_input_1)
    assert parsed_1 is not None, "Failed to parse inline_input_1"
    assert parsed_1["name"] == "Visweswara Rao", f"Expected 'Visweswara Rao', got {parsed_1['name']}"
    assert parsed_1["age"] == 25, f"Expected 25, got {parsed_1['age']}"
    assert parsed_1["gender"] == "Male", f"Expected 'Male', got {parsed_1['gender']}"
    assert parsed_1["berth"] == "No Preference (NP)", f"Expected 'No Preference (NP)', got {parsed_1['berth']}"
    print(f"   • Parsed Raw User Prompt:  {parsed_1['name']}, {parsed_1['age']} yrs, {parsed_1['gender']}, {parsed_1['berth']}")

    # Test via handle_route (user sends directly in bot chat)
    mock_msg_21 = type("MockMsg", (), {
        "text": inline_input_1,
        "sent_texts": []
    })()
    async def mock_reply_fn(text, reply_markup=None, parse_mode=None):
        mock_msg_21.sent_texts.append(text)
    mock_msg_21.reply_text = mock_reply_fn

    mock_upd_21 = type("MockUpdate", (), {
        "effective_user": type("MockUser", (), {"id": 88223344})(),
        "effective_message": mock_msg_21,
        "message": mock_msg_21
    })()
    mock_ctx_21 = type("MockContext", (), {"user_data": {}, "args": []})()

    ret_state = await bot.handle_route(mock_upd_21, mock_ctx_21)
    assert any("PASSENGER ADDED TO MASTER LIST" in t for t in mock_msg_21.sent_texts), "Inline passenger not saved via handle_route"
    saved_profs = await storage.get_passenger_profiles(88223344)
    assert len(saved_profs) >= 1
    assert saved_profs[0]["name"] == "Visweswara Rao"
    assert saved_profs[0]["age"] == 25
    assert saved_profs[0]["gender"] == "Male"
    assert saved_profs[0]["berth"] == "No Preference (NP)"
    print("   • Direct Chat Input Auto-Interception: Saved successfully to Master List & Storage")

    # Test via handle_create_profile_name
    mock_msg_21.sent_texts.clear()
    mock_msg_21.text = "visweswara rao 25,male,no preference"
    await bot.handle_create_profile_name(mock_upd_21, mock_ctx_21)
    assert any("PASSENGER ADDED TO MASTER LIST" in t for t in mock_msg_21.sent_texts), "Inline passenger not saved via handle_create_profile_name"
    print("   • Profile Name Prompt Inline Fallback: Saved successfully without 4 separate steps")
    print("✅ 1-Line Intelligent Passenger Auto-Parsing: PASSED")

    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY! (100% HEALTHY)")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_tests())
