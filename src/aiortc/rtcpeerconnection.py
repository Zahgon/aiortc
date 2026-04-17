import asyncio
import copy
import logging
import uuid
from typing import Optional, Union

from pyee.asyncio import AsyncIOEventEmitter

from . import clock, rtp, sdp
from .codecs import CODECS, HEADER_EXTENSIONS, is_rtx
from .events import RTCTrackEvent
from .exceptions import (
    InternalError,
    InvalidAccessError,
    InvalidStateError,
    OperationError,
)
from .mediastreams import MediaStreamTrack
from .rtcconfiguration import RTCBundlePolicy, RTCConfiguration
from .rtcdatachannel import RTCDataChannel, RTCDataChannelParameters
from .rtcdtlstransport import RTCCertificate, RTCDtlsParameters, RTCDtlsTransport
from .rtcicetransport import (
    RTCIceCandidate,
    RTCIceGatherer,
    RTCIceParameters,
    RTCIceTransport,
)
from .rtcrtpparameters import (
    RTCRtpCodecCapability,
    RTCRtpCodecParameters,
    RTCRtpDecodingParameters,
    RTCRtpHeaderExtensionParameters,
    RTCRtpParameters,
    RTCRtpReceiveParameters,
    RTCRtpRtxParameters,
    RTCRtpSendParameters,
)
from .rtcrtpreceiver import RemoteStreamTrack, RTCRtpReceiver
from .rtcrtpsender import RTCRtpSender
from .rtcrtptransceiver import RTCRtpTransceiver
from .rtcsctptransport import RTCSctpCapabilities, RTCSctpTransport
from .rtcsessiondescription import RTCSessionDescription
from .stats import RTCStatsReport

DISCARD_HOST = "0.0.0.0"
DISCARD_PORT = 9
MEDIA_KINDS = ["audio", "video"]

logger = logging.getLogger(__name__)


def filter_preferred_codecs(
    codecs: list[RTCRtpCodecParameters], preferred: list[RTCRtpCodecCapability]
) -> list[RTCRtpCodecParameters]:
    if not preferred:
        return codecs

    rtx_codecs = list(filter(is_rtx, codecs))
    rtx_enabled = next(filter(is_rtx, preferred), None) is not None

    filtered = []
    for pref in filter(lambda x: not is_rtx(x), preferred):
        for codec in codecs:
            if (
                codec.mimeType.lower() == pref.mimeType.lower()
                and codec.parameters == pref.parameters
            ):
                filtered.append(codec)

                # add corresponding RTX
                if rtx_enabled:
                    for rtx in rtx_codecs:
                        if rtx.parameters["apt"] == codec.payloadType:
                            filtered.append(rtx)
                            break

                break

    return filtered


def find_common_codecs(
    local_codecs: list[RTCRtpCodecParameters],
    remote_codecs: list[RTCRtpCodecParameters],
) -> list[RTCRtpCodecParameters]:
    common = []
    common_base: dict[int, RTCRtpCodecParameters] = {}
    for c in remote_codecs:
        # for RTX, check we accepted the base codec
        if is_rtx(c):
            apt = c.parameters.get("apt")
            if isinstance(apt, int) and apt in common_base:
                base = common_base[apt]
                if c.clockRate == base.clockRate:
                    common.append(copy.deepcopy(c))
            continue

        # handle other codecs
        for codec in local_codecs:
            if is_codec_compatible(codec, c):
                codec = copy.deepcopy(codec)
                if c.payloadType in rtp.DYNAMIC_PAYLOAD_TYPES:
                    codec.payloadType = c.payloadType
                codec.rtcpFeedback = list(
                    filter(lambda x: x in c.rtcpFeedback, codec.rtcpFeedback)
                )
                common.append(codec)
                common_base[codec.payloadType] = codec
                break
    return common


def find_common_header_extensions(
    local_extensions: list[RTCRtpHeaderExtensionParameters],
    remote_extensions: list[RTCRtpHeaderExtensionParameters],
) -> list[RTCRtpHeaderExtensionParameters]:
    pass


def is_codec_compatible(a: RTCRtpCodecParameters, b: RTCRtpCodecParameters) -> bool:
    if a.mimeType.lower() != b.mimeType.lower() or a.clockRate != b.clockRate:
        return False

    if a.mimeType.lower() == "video/h264":

        def packetization(c: RTCRtpCodecParameters) -> int:
            return int(c.parameters.get("packetization-mode", "0"))

        def profile(c: RTCRtpCodecParameters) -> sdp.H264Profile:
            # for backwards compatibility with older versions of WebRTC,
            # consider the absence of a profile-level-id parameter to mean
            # "constrained baseline level 3.1"
            return sdp.parse_h264_profile_level_id(
                str(c.parameters.get("profile-level-id", "42E01F"))
            )[0]

        try:
            return packetization(a) == packetization(b) and profile(a) == profile(b)
        except ValueError:
            return False

    return True


def add_transport_description(
    media: sdp.MediaDescription, dtlsTransport: RTCDtlsTransport
) -> None:
    # ice
    pass


async def add_remote_candidates(
    iceTransport: RTCIceTransport, media: sdp.MediaDescription
) -> None:
    pass


def allocate_mid(mids: set[str]) -> str:
    """
    Allocate a MID which has not been used yet.
    """
    pass


def create_media_description_for_sctp(
    sctp: RTCSctpTransport, legacy: bool, mid: str
) -> sdp.MediaDescription:
    pass


def create_media_description_for_transceiver(
    transceiver: RTCRtpTransceiver, cname: str, direction: str, mid: str
) -> sdp.MediaDescription:
    pass


def and_direction(a: str, b: str) -> str:
    pass


def or_direction(a: str, b: str) -> str:
    pass


def reverse_direction(direction: str) -> str:
    pass


def wrap_session_description(
    session_description: Optional[sdp.SessionDescription],
) -> Optional[RTCSessionDescription]:
    pass


class RTCPeerConnection(AsyncIOEventEmitter):
    """
    The :class:`RTCPeerConnection` interface represents a WebRTC connection
    between the local computer and a remote peer.

    :param configuration: An optional :class:`RTCConfiguration`.
    """

    def __init__(self, configuration: Optional[RTCConfiguration] = None) -> None:
        super().__init__()
        self.__certificates = [RTCCertificate.generateCertificate()]
        self.__cname = f"{uuid.uuid4()}"
        self.__configuration = configuration or RTCConfiguration()
        self.__dtlsTransports: set[RTCDtlsTransport] = set()
        self.__iceTransports: set[RTCIceTransport] = set()
        self.__remoteDtls: dict[
            Union[RTCRtpTransceiver, RTCSctpTransport], RTCDtlsParameters
        ] = {}
        self.__remoteIce: dict[
            Union[RTCRtpTransceiver, RTCSctpTransport], RTCIceParameters
        ] = {}
        self.__seenMids: set[str] = set()
        self.__sctp: Optional[RTCSctpTransport] = None
        self.__sctp_mline_index: Optional[int] = None
        # By default we use "UDP/DTLS/SCTP" in our SDP, but we also
        # accept "DTLS/SCTP" from older browsers.
        self._sctpLegacySdp = False
        self.__sctpRemotePort: Optional[int] = None
        self.__sctpRemoteCaps: Optional[RTCSctpCapabilities] = None
        self.__stream_id = str(uuid.uuid4())
        self.__transceivers: list[RTCRtpTransceiver] = []

        self.__closeTask: Optional[asyncio.Task] = None
        self.__connectionState = "new"
        self.__iceConnectionState = "new"
        self.__iceGatheringState = "new"
        self.__isClosed: Optional[asyncio.Future[bool]] = None
        self.__signalingState = "stable"

        self.__currentLocalDescription: Optional[sdp.SessionDescription] = None
        self.__currentRemoteDescription: Optional[sdp.SessionDescription] = None
        self.__pendingLocalDescription: Optional[sdp.SessionDescription] = None
        self.__pendingRemoteDescription: Optional[sdp.SessionDescription] = None

    @property
    def connectionState(self) -> str:
        """
        The current connection state.

        Possible values: `"connected"`, `"connecting"`, `"closed"`, `"failed"`, `"new`".

        When the state changes, the `"connectionstatechange"` event is fired.
        """
        pass

    @property
    def iceConnectionState(self) -> str:
        """
        The current ICE connection state.

        Possible values: `"checking"`, `"completed"`, `"closed"`, `"failed"`, `"new`".

        When the state changes, the `"iceconnectionstatechange"` event is fired.
        """
        pass

    @property
    def iceGatheringState(self) -> str:
        """
        The current ICE gathering state.

        Possible values: `"complete"`, `"gathering"`, `"new`".

        When the state changes, the `"icegatheringstatechange"` event is fired.
        """
        pass

    @property
    def localDescription(self) -> RTCSessionDescription:
        """
        An :class:`RTCSessionDescription` describing the session for
        the local end of the connection.
        """
        pass

    @property
    def remoteDescription(self) -> RTCSessionDescription:
        """
        An :class:`RTCSessionDescription` describing the session for
        the remote end of the connection.
        """
        pass

    @property
    def sctp(self) -> Optional[RTCSctpTransport]:
        """
        An :class:`RTCSctpTransport` describing the SCTP transport being used
        for datachannels or `None`.
        """
        pass

    @property
    def signalingState(self) -> str:
        """
        The current signaling state.

        Possible values: `"closed"`, `"have-local-offer"`, `"have-remote-offer`",
        `"stable"`.

        When the state changes, the `"signalingstatechange"` event is fired.
        """
        pass

    async def addIceCandidate(self, candidate: Optional[RTCIceCandidate]) -> None:
        """
        Add a new :class:`RTCIceCandidate` received from the remote peer.

        The specified candidate must have a value for either `sdpMid` or
        `sdpMLineIndex`.

        :param candidate: The new remote candidate or `None` to signal
                            end-of-candidates.
        """
        pass

    def addTrack(self, track: MediaStreamTrack) -> RTCRtpSender:
        """
        Add a :class:`MediaStreamTrack` to the set of media tracks which
        will be transmitted to the remote peer.
        """
        pass

    def addTransceiver(
        self, trackOrKind: Union[str, MediaStreamTrack], direction: str = "sendrecv"
    ) -> RTCRtpTransceiver:
        """
        Add a new :class:`RTCRtpTransceiver`.
        """
        pass

    async def close(self) -> None:
        """
        Terminate the ICE agent, ending ICE processing and streams.
        """
        if self.__isClosed:
            await self.__isClosed
            return
        self.__isClosed = asyncio.Future()
        self.__setSignalingState("closed")

        # stop senders / receivers
        for transceiver in self.__transceivers:
            await transceiver.stop()
        if self.__sctp:
            await self.__sctp.stop()

        # stop transports
        for transceiver in self.__transceivers:
            await transceiver.receiver.transport.stop()
            await transceiver.receiver.transport.transport.stop()
        if self.__sctp:
            await self.__sctp.transport.stop()
            await self.__sctp.transport.transport.stop()

        # update states
        self.__updateIceGatheringState()
        self.__updateIceConnectionState()
        self.__updateConnectionState()

        # no more events will be emitted, so remove all event listeners
        # to facilitate garbage collection.
        self.remove_all_listeners()

        self.__isClosed.set_result(True)

    async def createAnswer(self) -> RTCSessionDescription:
        """
        Create an SDP answer to an offer received from a remote peer during
        the offer/answer negotiation of a WebRTC connection.

        :rtype: :class:`RTCSessionDescription`
        """
        pass

    def createDataChannel(
        self,
        label: str,
        maxPacketLifeTime: Optional[int] = None,
        maxRetransmits: Optional[int] = None,
        ordered: bool = True,
        protocol: str = "",
        negotiated: bool = False,
        id: Optional[int] = None,
    ) -> RTCDataChannel:
        """
        Create a data channel with the given label.

        :rtype: :class:`RTCDataChannel`
        """
        pass

    async def createOffer(self) -> RTCSessionDescription:
        """
        Create an SDP offer for the purpose of starting a new WebRTC
        connection to a remote peer.

        :rtype: :class:`RTCSessionDescription`
        """
        pass

    def getReceivers(self) -> list[RTCRtpReceiver]:
        """
        Returns the list of :class:`RTCRtpReceiver` objects that are currently
        attached to the connection.
        """
        pass

    def getSenders(self) -> list[RTCRtpSender]:
        """
        Returns the list of :class:`RTCRtpSender` objects that are currently
        attached to the connection.
        """
        pass

    async def getStats(self) -> RTCStatsReport:
        """
        Returns statistics for the connection.

        :rtype: :class:`RTCStatsReport`
        """
        pass

    def getTransceivers(self) -> list[RTCRtpTransceiver]:
        """
        Returns the list of :class:`RTCRtpTransceiver` objects that are currently
        attached to the connection.
        """
        pass

    async def setLocalDescription(
        self, sessionDescription: Optional[RTCSessionDescription] = None
    ) -> None:
        """
        Change the local description associated with the connection.

        :param sessionDescription: An :class:`RTCSessionDescription` generated
                                    by :meth:`createOffer` or :meth:`createAnswer()`
                                    or `None` to implicitly create an offer or create
                                    an answer, as needed.
        """
        pass

    async def setRemoteDescription(
        self, sessionDescription: RTCSessionDescription
    ) -> None:
        """
        Changes the remote description associated with the connection.

        :param sessionDescription: An :class:`RTCSessionDescription` created from
                                    information received over the signaling channel.
        """
        pass

    async def __connect(self) -> None:
        pass

    async def __gather(self) -> None:
        pass

    def __assertNotClosed(self) -> None:
        pass

    def __assertTrackHasNoSender(self, track: MediaStreamTrack) -> None:
        pass

    def __createDtlsTransport(self) -> RTCDtlsTransport:
        # create ICE transport
        pass

    def __createSctpTransport(self) -> None:
        pass

    def __createTransceiver(
        self, direction: str, kind: str, sender_track: Optional[MediaStreamTrack] = None
    ) -> RTCRtpTransceiver:
        pass

    def __getTransceiverByMid(self, mid: str) -> Optional[RTCRtpTransceiver]:
        pass

    def __getTransceiverByMLineIndex(self, index: int) -> Optional[RTCRtpTransceiver]:
        pass

    def __localDescription(self) -> Optional[sdp.SessionDescription]:
        pass

    def __localRtp(self, transceiver: RTCRtpTransceiver) -> RTCRtpSendParameters:
        pass

    def __log_debug(self, msg: str, *args: object) -> None:
        logger.debug(f"RTCPeerConnection() {msg}", *args)

    def __remoteDescription(self) -> Optional[sdp.SessionDescription]:
        pass

    def __remoteRtp(self, transceiver: RTCRtpTransceiver) -> RTCRtpReceiveParameters:
        pass

    def __setSignalingState(self, state: str) -> None:
        self.__signalingState = state
        self.emit("signalingstatechange")

    def __updateConnectionState(self) -> None:
        # compute new state
        # NOTE: we do not have a "disconnected" state
        dtlsStates = set(map(lambda x: x.state, self.__dtlsTransports))
        iceStates = set(map(lambda x: x.state, self.__iceTransports))
        if self.__isClosed:
            state = "closed"
        elif "failed" in iceStates or "failed" in dtlsStates:
            state = "failed"
        elif not iceStates.difference(["new", "closed"]) and not dtlsStates.difference(
            ["new", "closed"]
        ):
            state = "new"
        elif "checking" in iceStates or "connecting" in dtlsStates:
            state = "connecting"
        elif "new" in dtlsStates:
            # this avoids a spurious connecting -> connected -> connecting
            # transition after ICE connects but before DTLS starts
            state = "connecting"
        else:
            state = "connected"

        # update state
        if state != self.__connectionState:
            self.__log_debug("connectionState %s -> %s", self.__connectionState, state)
            self.__connectionState = state
            self.emit("connectionstatechange")

        # if all DTLS connections are closed, initiate a shutdown
        if (
            not self.__isClosed
            and self.__closeTask is None
            and dtlsStates == set(["closed"])
        ):
            self.__closeTask = asyncio.ensure_future(self.close())

    def __updateIceConnectionState(self) -> None:
        # compute new state
        # NOTE: we do not have "connected" or "disconnected" states
        states = set(map(lambda x: x.state, self.__iceTransports))
        if self.__isClosed:
            state = "closed"
        elif "failed" in states:
            state = "failed"
        elif states == set(["completed"]):
            state = "completed"
        elif "checking" in states:
            state = "checking"
        else:
            state = "new"

        # update state
        if state != self.__iceConnectionState:
            self.__log_debug(
                "iceConnectionState %s -> %s", self.__iceConnectionState, state
            )
            self.__iceConnectionState = state
            self.emit("iceconnectionstatechange")

    def __updateIceGatheringState(self) -> None:
        # compute new state
        states = set(map(lambda x: x.iceGatherer.state, self.__iceTransports))
        if states == set(["completed"]):
            state = "complete"
        elif "gathering" in states:
            state = "gathering"
        else:
            state = "new"

        # update state
        if state != self.__iceGatheringState:
            self.__log_debug(
                "iceGatheringState %s -> %s", self.__iceGatheringState, state
            )
            self.__iceGatheringState = state
            self.emit("icegatheringstatechange")

    def __validate_description(
        self, description: sdp.SessionDescription, is_local: bool
    ) -> None:
        # check description is compatible with signaling state
        pass
