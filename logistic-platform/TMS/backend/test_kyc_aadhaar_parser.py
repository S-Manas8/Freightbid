import io
import unittest
from pathlib import Path

from backend.routers.kyc import (
    _convert_uploaded_image_to_grayscale,
    _convert_uploaded_pan_to_grayscale,
    _enhance_aadhaar_extraction,
    _enhance_driving_license_extraction,
    _enhance_pan_extraction,
    _extract_aadhaar_fields,
    _extract_driving_license_fields,
    _extract_pan_fields,
    _make_dl_number_crops,
    _read_pan_dob_from_image,
)


class AadhaarParserTest(unittest.TestCase):
    def test_extracts_front_side_fields_from_common_aadhaar_text(self):
        raw_text = """
        Government of India
        Sutapa Pal Datta
        Date of Birth/DOB: 26/01/1979
        Female/ FEMALE
        6641 2804 9316
        VID : 9179 3343 7087 9130
        Aadhaar
        """

        fields = _extract_aadhaar_fields(raw_text)

        self.assertEqual(fields["name"], "Sutapa Pal Datta")
        self.assertEqual(fields["dob"], "26/01/1979")
        self.assertEqual(fields["gender"], "Female")
        self.assertEqual(fields["id_number"], "6641 2804 9316")

    def test_enhancement_keeps_existing_ocr_fields(self):
        payload = {
            "raw_text": "Aadhaar\nOCR Name\nDOB: 01/02/1990\nMale\n2345 6789 1234",
            "extracted_fields": {"name": "Existing Name"},
        }

        enhanced = _enhance_aadhaar_extraction(payload, source="aadhaar")

        self.assertEqual(enhanced["extracted_fields"]["name"], "Existing Name")
        self.assertEqual(enhanced["extracted_fields"]["dob"], "01/02/1990")
        self.assertEqual(enhanced["extracted_fields"]["id_number"], "2345 6789 1234")
        self.assertEqual(enhanced["doc_type"], "aadhaar")

    def test_aadhaar_enhancement_removes_non_required_fields(self):
        payload = {
            "raw_text": "Aadhaar\nOCR Name\nDOB: 01/02/1990\nMale\n2345 6789 1234",
            "extracted_fields": {
                "name": "OCR Name",
                "dob": "01/02/1990",
                "gender": "Male",
                "father_name": "Some Father",
                "address": "Some Address",
            },
        }

        enhanced = _enhance_aadhaar_extraction(payload, source="aadhaar")

        self.assertEqual(
            set(enhanced["extracted_fields"].keys()),
            {"name", "dob", "id_number"},
        )


class PanParserTest(unittest.TestCase):
    def test_pan_image_converter_outputs_grayscale_image(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest("Pillow is not available")

        source = Image.new("RGB", (2, 1))
        source.putpixel((0, 0), (255, 0, 0))
        source.putpixel((1, 0), (0, 128, 255))
        buf = io.BytesIO()
        source.save(buf, format="PNG")

        converted, content_type = _convert_uploaded_pan_to_grayscale(buf.getvalue(), "image/png")

        self.assertEqual(content_type, "image/png")
        result = Image.open(io.BytesIO(converted))
        self.assertEqual(result.mode, "L")

    def test_pan_image_converter_crops_and_upscales_card_text_area(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest("Pillow is not available")

        source = Image.new("RGB", (300, 120), (255, 255, 255))
        buf = io.BytesIO()
        source.save(buf, format="JPEG")

        converted, content_type = _convert_uploaded_pan_to_grayscale(buf.getvalue(), "image/jpeg")

        self.assertEqual(content_type, "image/jpeg")
        result = Image.open(io.BytesIO(converted))
        self.assertEqual(result.mode, "L")
        self.assertEqual(result.size, (648, 360))

    def test_extracts_pan_front_side_fields(self):
        raw_text = """
        Permanent Account Number Card
        GNAPM9225C
        Name
        SAMALETI MANAS
        Father's Name
        SAMALETI SHAILENDER KUMAR
        Date of Birth
        12/07/1998
        """

        fields = _extract_pan_fields(raw_text)

        self.assertEqual(fields["id_number"], "GNAPM9225C")
        self.assertEqual(fields["name"], "SAMALETI MANAS")
        self.assertEqual(fields["father_name"], "SAMALETI SHAILENDER KUMAR")
        self.assertEqual(fields["dob"], "12/07/1998")

    def test_extracts_pan_fields_from_front_card_layout_labels(self):
        raw_text = """
        INCOME TAX DEPARTMENT
        Permanent Account Number Card
        ABCDE1234F
        PHOTO
        Name of Person
        RAVI KUMAR SHARMA
        Father's Name
        MAHESH CHANDRA SHARMA
        Date of Birth
        09/05/1991
        Signature
        """

        fields = _extract_pan_fields(raw_text)

        self.assertEqual(fields["id_number"], "ABCDE1234F")
        self.assertEqual(fields["name"], "RAVI KUMAR SHARMA")
        self.assertEqual(fields["father_name"], "MAHESH CHANDRA SHARMA")
        self.assertEqual(fields["dob"], "09/05/1991")

    def test_extracts_pan_names_by_layout_when_ocr_misses_labels(self):
        raw_text = """
        Permanent Account Number Card
        ABCDE1234F
        RAVI KUMAR SHARMA
        MAHESH CHANDRA SHARMA
        09/05/1991
        """

        fields = _extract_pan_fields(raw_text)

        self.assertEqual(fields["id_number"], "ABCDE1234F")
        self.assertEqual(fields["name"], "RAVI KUMAR SHARMA")
        self.assertEqual(fields["father_name"], "MAHESH CHANDRA SHARMA")
        self.assertEqual(fields["dob"], "09/05/1991")

    def test_pan_enhancement_replaces_existing_ocr_guesses(self):
        payload = {
            "raw_text": "PAN\nABCDE1234F\nName\nOCR NAME\nFather Name\nFATHER PERSON\nDOB 01/01/1990",
            "extracted_fields": {"name": "Wrong OCR Guess"},
        }

        enhanced = _enhance_pan_extraction(payload, source="pan")

        self.assertEqual(enhanced["extracted_fields"]["name"], "OCR NAME")
        self.assertEqual(enhanced["extracted_fields"]["father_name"], "FATHER PERSON")
        self.assertEqual(enhanced["extracted_fields"]["dob"], "01/01/1990")
        self.assertEqual(enhanced["extracted_fields"]["id_number"], "ABCDE1234F")
        self.assertEqual(enhanced["doc_type"], "pan")

    def test_pan_enhancement_removes_partial_bad_fields(self):
        payload = {
            "raw_text": "Permanent Account Number Card\nGNAPM9225C",
            "extracted_fields": {"name": "STEE FATT ANA UT", "father_name": "SART FER FER WE"},
        }

        enhanced = _enhance_pan_extraction(payload, source="pan")

        self.assertEqual(enhanced["extracted_fields"], {"id_number": "GNAPM9225C"})

    def test_pan_name_cleanup_removes_noise_and_recovers_surname(self):
        raw_text = """
        Permanent Account Number Card
        GNAPM9225C
        Name
        AMALETI MANAS WE CE
        Father's Name
        SAMALETI SHAILENDER KUMAR
        """

        fields = _extract_pan_fields(raw_text)

        self.assertEqual(fields["name"], "SAMALETI MANAS")
        self.assertEqual(fields["father_name"], "SAMALETI SHAILENDER KUMAR")

    def test_pan_dob_handles_ocr_digit_confusion(self):
        raw_text = """
        Permanent Account Number Card
        GNAPM9225C
        Name
        SAMALETI MANAS
        Father's Name
        SAMALETI SHAILENDER KUMAR
        Date of Birth
        O8/11/2OO4
        """

        fields = _extract_pan_fields(raw_text)

        self.assertEqual(fields["dob"], "08/11/2004")

    def test_pan_dob_image_reader_on_sample_card_if_available(self):
        sample = Path(r"C:\Users\hp\Downloads\manaspancard.jpeg")
        if not sample.exists():
            self.skipTest("local sample PAN card is not available")

        self.assertEqual(_read_pan_dob_from_image(sample.read_bytes()), "08/11/2004")


class DrivingLicenseParserTest(unittest.TestCase):
    def test_dl_image_converter_outputs_full_grayscale_image(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest("Pillow is not available")

        source = Image.new("RGB", (220, 120), (255, 255, 255))
        buf = io.BytesIO()
        source.save(buf, format="JPEG")

        converted, content_type = _convert_uploaded_image_to_grayscale(buf.getvalue(), "image/jpeg")

        self.assertEqual(content_type, "image/jpeg")
        result = Image.open(io.BytesIO(converted))
        self.assertEqual(result.mode, "L")
        self.assertEqual(result.size, (660, 360))

    def test_dl_number_crops_focus_top_red_number_area(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest("Pillow is not available")

        source = Image.new("RGB", (1000, 600), (255, 255, 255))
        buf = io.BytesIO()
        source.save(buf, format="JPEG")

        crops = _make_dl_number_crops(buf.getvalue())

        self.assertGreaterEqual(len(crops), 6)
        crop = Image.open(io.BytesIO(crops[0][1]))
        self.assertEqual(crop.mode, "L")
        self.assertEqual(crop.size, (2400, 360))

    def test_extracts_dl_front_fields_with_labelled_name_and_dob(self):
        raw_text = """
        Driving Licence
        TG01220260004928
        Name : SAMALETI MANAS
        Date Of Birth : 08-11-2004
        Blood Group Unknown
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["id_number"], "TG01220260004928")
        self.assertEqual(fields["name"], "SAMALETI MANAS")
        self.assertEqual(fields["dob"], "08/11/2004")

    def test_extracts_dl_name_without_holder_signature_noise(self):
        raw_text = """
        Driving Licence
        TG01220260004928
        Name : SAMALETI MANAS Holder's Signature
        Date Of Birth : 08-11-2004
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["name"], "SAMALETI MANAS")


    def test_extracts_dl_number_when_ocr_confuses_zero(self):
        raw_text = """
        Driving Licence
        TGO122026OOO4928
        Name : SAMALETI MANAS Date Of Birth : 08-11-2004
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["id_number"], "TG01220260004928")
        self.assertEqual(fields["name"], "SAMALETI MANAS")
        self.assertEqual(fields["dob"], "08/11/2004")

    def test_dl_enhancement_rejects_short_garbage_upstream_name(self):
        payload = {
            "raw_text": "Driving Licence\nTGO122026OOO4928\nDate Of Birth 08/11/2004",
            "extracted_fields": {"name": "a yr ae"},
            "validation_errors": ["Extracted name is too short to be valid"],
        }

        enhanced = _enhance_driving_license_extraction(payload, source="dl")

        self.assertEqual(enhanced["extracted_fields"]["id_number"], "TG01220260004928")
        self.assertEqual(enhanced["extracted_fields"]["license_number"], "TG01220260004928")
        self.assertNotIn("name", enhanced["extracted_fields"])
        self.assertNotIn("Extracted name is too short to be valid", enhanced["validation_errors"])

    def test_extracts_dl_name_from_line_above_care_of_when_name_label_missing(self):
        raw_text = """
        Driving Licence
        TG01220260004928
        SAMALETI MANAS
        C/O S S SHAILENDER KUMAR
        Date Of Birth : 08-11-2004
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["id_number"], "TG01220260004928")
        self.assertEqual(fields["name"], "SAMALETI MANAS")
        self.assertEqual(fields["dob"], "08/11/2004")

    def test_extracts_dl_name_before_care_of_on_same_line(self):
        raw_text = """
        Driving Licence
        TG01220260004928
        SAMALETI MANAS C/O S S SHAILENDER KUMAR
        DOB 08/11/2004
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["name"], "SAMALETI MANAS")

    def test_extracts_dl_holder_with_initials_above_care_of(self):
        raw_text = """
        INDIAN UNION DRIVING LICENCE
        ANDHRA PRADESH
        AP01620210039092
        L V BHARGAV
        C/O LAKKAMRAJU VENKATA N
        CHAGARLAMUDI VARI STREET
        Issued On: 23-07-2021
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["id_number"], "AP01620210039092")
        self.assertEqual(fields["name"], "L V BHARGAV")

    def test_extracts_dl_holder_from_merged_line_before_care_of(self):
        raw_text = """
        INDIAN UNION DRIVING LICENCE ANDHRA PRADESH AP01620210039092 L V BHARGAV C/O LAKKAMRAJU VENKATA N
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["id_number"], "AP01620210039092")
        self.assertEqual(fields["name"], "L V BHARGAV")

    def test_dl_enhancement_replaces_state_name_with_care_of_holder(self):
        payload = {
            "raw_text": "INDIAN UNION DRIVING LICENCE\nANDHRA PRADESH\nAP01620210039092\nL V BHARGAV\nC/O LAKKAMRAJU VENKATA N",
            "extracted_fields": {"name": "ANDHRA PRADESH"},
        }

        enhanced = _enhance_driving_license_extraction(payload, source="dl")

        self.assertEqual(enhanced["extracted_fields"]["license_number"], "AP01620210039092")
        self.assertEqual(enhanced["extracted_fields"]["name"], "L V BHARGAV")

    def test_extracts_dl_dob_from_back_side_text(self):
        raw_text = """
        Class of Vehicle Code Issued by Date of Issue
        Date of Birth
        08/11/2004
        Vehicle Category NT
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["dob"], "08/11/2004")
        self.assertNotIn("name", fields)

    def test_dl_dob_ignores_first_issue_and_uses_date_of_birth_label(self):
        raw_text = """
        Reference No. AP01620210039092
        Original LA. RTA VIJAYAWADA
        Date of First Issue 23-07-2021
        Date of Birth 27-06-2002
        Blood Group A+
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertEqual(fields["id_number"], "AP01620210039092")
        self.assertEqual(fields["dob"], "27/06/2002")

    def test_dl_dob_does_not_use_unlabelled_issue_date(self):
        raw_text = """
        Reference No. AP01620210039092
        Original LA. RTA VIJAYAWADA
        Date of First Issue 23-07-2021
        """

        fields = _extract_driving_license_fields(raw_text)

        self.assertNotIn("dob", fields)

    def test_dl_enhancement_keeps_only_required_dl_fields(self):
        payload = {
            "raw_text": "Driving Licence\nTG01220260004928\nName\nSAMALETI MANAS\nDOB 08/11/2004",
            "extracted_fields": {"name": "Bad OCR", "gender": "Male"},
        }

        enhanced = _enhance_driving_license_extraction(payload, source="dl")

        self.assertEqual(enhanced["extracted_fields"]["id_number"], "TG01220260004928")
        self.assertEqual(enhanced["extracted_fields"]["license_number"], "TG01220260004928")
        self.assertEqual(enhanced["extracted_fields"]["name"], "SAMALETI MANAS")
        self.assertEqual(enhanced["extracted_fields"]["dob"], "08/11/2004")
        self.assertEqual(enhanced["doc_type"], "driving_license")


if __name__ == "__main__":
    unittest.main()
