from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Boolean, Integer, Text as TEXT
from .database import Base
import uuid
import datetime
def gen_id():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id              = Column(TEXT, primary_key=True, default=gen_id)
    name            = Column(String, nullable=False)
    email           = Column(String, unique=True, nullable=False)
    password        = Column(String, nullable=False)
    role            = Column(String, nullable=False)   # "shipper" or "driver"
    phone           = Column(String)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)

    # eKYC fields (drivers only)
    kyc_status      = Column(String, default="pending")   # pending / verified / rejected / manual_review
    kyc_session_id  = Column(String, nullable=True)       # eKYC session_id reference
    license_number  = Column(String, nullable=True)       # auto-extracted from DL during KYC
    aadhaar_number  = Column(String, nullable=True)
    pan_number      = Column(String, nullable=True)
    kyc_name        = Column(String, nullable=True)
    kyc_dob         = Column(String, nullable=True)
    kyc_review_reason = Column(TEXT, nullable=True)
    kyc_review_details = Column(TEXT, nullable=True)
    kyc_verified_at = Column(DateTime, nullable=True)
    verification    = Column(String, default="no")        # "yes" or "no"




class Shipment(Base):
    __tablename__ = "shipments"

    id                 = Column(TEXT, primary_key=True, default=gen_id)
    shipper_id         = Column(TEXT, ForeignKey("users.id"), nullable=False)
    pickup_address     = Column(String, nullable=False)
    pickup_lat         = Column(Float, nullable=True)
    pickup_lng         = Column(Float, nullable=True)
    drop_address       = Column(String, nullable=True)
    goods_desc         = Column(String, nullable=True)
    weight_kg          = Column(Float, nullable=False, default=0)
    vehicle_type       = Column(String, default="Truck")
    deadline           = Column(DateTime, nullable=True)
    est_time_hours     = Column(Float, nullable=True)
    parent_shipment_id = Column(TEXT, nullable=True)
    num_trucks         = Column(Integer, nullable=False, default=1)

    # Status flow: open → assigned → in_transit → delivered
    status             = Column(String, default="open")
    assigned_driver_id = Column(TEXT, ForeignKey("users.id"), nullable=True)
    winning_bid_amount = Column(Float, nullable=True)
    freight_adjusted_amount = Column(Float, nullable=True)
    freight_adjustment_delta = Column(Float, nullable=True)
    freight_adjustment_status = Column(String, default="none")  # none / pending / accepted / paid / rejected
    freight_adjustment_note = Column(TEXT, nullable=True)
    freight_adjustment_pi_id = Column(String, nullable=True)
    freight_adjustment_requested_at = Column(DateTime, nullable=True)
    freight_adjustment_accepted_at = Column(DateTime, nullable=True)
    freight_adjustment_paid_at = Column(DateTime, nullable=True)

    created_at   = Column(DateTime, default=datetime.datetime.utcnow)
    started_at   = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)


class ShipmentDestination(Base):
    __tablename__ = "shipment_destinations"

    id          = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    address     = Column(String, nullable=False)
    lat         = Column(Float, default=0.0)
    lng         = Column(Float, default=0.0)
    order_index = Column(Integer, default=0)
    status      = Column(String, default="pending")  # pending / delivered

    # Acknowledgement flow:
    #   none              → driver has not arrived yet
    #   pending_approval  → driver clicked "I've Arrived", waiting for shipper
    #   approved          → shipper approved, driver can now mark delivered
    ack_status  = Column(String, default="none")


class Bid(Base):
    __tablename__ = "bids"

    id          = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    driver_id   = Column(TEXT, ForeignKey("users.id"), nullable=False)
    amount      = Column(Float, nullable=False)
    is_winner   = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id          = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    driver_id   = Column(TEXT, ForeignKey("users.id"), nullable=False)
    lat         = Column(Float, nullable=False)
    lng         = Column(Float, nullable=False)
    timestamp   = Column(DateTime, default=datetime.datetime.utcnow)


class POD(Base):
    __tablename__ = "pods"

    id           = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id  = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    dest_id      = Column(TEXT, ForeignKey("shipment_destinations.id"), nullable=True)
    image_url    = Column(String)
    geo_lat      = Column(Float)
    geo_lng      = Column(Float)
    delivered_at = Column(DateTime, default=datetime.datetime.utcnow)
    notes        = Column(String)
    pod_type     = Column(String, default="delivery")  # "delivery" or "proof_request"
    
    # Shipper acknowledgement flow
    ack_status   = Column(String, default="pending")  # pending / approved / rejected
    ack_notes    = Column(String, nullable=True)      # shipper's feedback on rejection
    ack_at       = Column(DateTime, nullable=True)    # when shipper acknowledged


class Complaint(Base):
    __tablename__ = "complaints"

    id          = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    shipper_id  = Column(TEXT, ForeignKey("users.id"), nullable=False)
    driver_id   = Column(TEXT, ForeignKey("users.id"), nullable=False)
    reason      = Column(String, nullable=False)
    description = Column(TEXT, nullable=True)
    status      = Column(String, default="open")  # open / resolved / dismissed
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class ProofRequest(Base):
    __tablename__ = "proof_requests"

    id          = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    shipper_id  = Column(TEXT, ForeignKey("users.id"), nullable=False)
    status      = Column(String, default="pending")   # pending / fulfilled
    image_url   = Column(String, nullable=True)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
    fulfilled_at = Column(DateTime, nullable=True)


class Payment(Base):
    __tablename__ = "payments"

    id                 = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id        = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    shipper_id         = Column(TEXT, ForeignKey("users.id"), nullable=False)
    driver_id          = Column(TEXT, ForeignKey("users.id"), nullable=False)
    amount             = Column(Float, nullable=False)          # in INR (rupees)
    currency           = Column(String, default="inr")
    stripe_pi_id       = Column(String, nullable=True)          # payment_intent id
    stripe_pm_id       = Column(String, nullable=True)          # payment_method id
    stripe_charge_id   = Column(String, nullable=True)          # charge id
    status             = Column(String, default="pending")      # pending / succeeded / failed
    card_last4         = Column(String, nullable=True)
    card_brand         = Column(String, nullable=True)
    created_at         = Column(DateTime, default=datetime.datetime.utcnow)
    paid_at            = Column(DateTime, nullable=True)
    driver_fee         = Column(Float, nullable=True)
    shipper_refund     = Column(Float, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id          = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    driver_id   = Column(TEXT, ForeignKey("users.id"), nullable=True)
    sender_id   = Column(TEXT, ForeignKey("users.id"), nullable=False)
    sender_role = Column(String, nullable=False)   # "shipper" or "driver"
    body        = Column(TEXT, nullable=False)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
    read_at     = Column(DateTime, nullable=True)


class DestinationChangeRequest(Base):
    __tablename__ = "destination_change_requests"

    id              = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id     = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    dest_id         = Column(TEXT, ForeignKey("shipment_destinations.id"), nullable=False)
    shipper_id      = Column(TEXT, ForeignKey("users.id"), nullable=False)
    driver_id       = Column(TEXT, ForeignKey("users.id"), nullable=False)
    new_address     = Column(String, nullable=False)
    new_lat         = Column(Float, nullable=True)
    new_lng         = Column(Float, nullable=True)
    status          = Column(String, default="pending")  # pending / accepted / rejected
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
    responded_at    = Column(DateTime, nullable=True)


class CancellationRecord(Base):
    __tablename__ = "cancellation_records"

    id              = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id     = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    shipper_id      = Column(TEXT, ForeignKey("users.id"), nullable=False)
    driver_id       = Column(TEXT, ForeignKey("users.id"), nullable=True)
    reason          = Column(String, nullable=False)
    scenario        = Column(String, nullable=False)   # no_penalty / assigned_penalty / in_transit_penalty
    trip_amount     = Column(Float, default=0)
    driver_fee      = Column(Float, default=0)
    shipper_refund  = Column(Float, default=0)
    km_travelled    = Column(Float, nullable=True)
    total_route_km  = Column(Float, nullable=True)
    completed_stops = Column(Integer, nullable=True)
    total_stops     = Column(Integer, nullable=True)
    cancelled_at    = Column(DateTime, default=datetime.datetime.utcnow)


class Rating(Base):
    __tablename__ = "ratings"

    id          = Column(TEXT, primary_key=True, default=gen_id)
    shipment_id = Column(TEXT, ForeignKey("shipments.id"), nullable=False)
    driver_id   = Column(TEXT, ForeignKey("users.id"), nullable=False)
    shipper_id  = Column(TEXT, ForeignKey("users.id"), nullable=False)
    score       = Column(Float, nullable=False)  # 1 to 5
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
       

