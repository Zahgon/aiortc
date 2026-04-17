import logging
from typing import Optional

from .codecs import get_capabilities
from .rtcrtpparameters import (
    RTCRtpCodecCapability,
    RTCRtpCodecParameters,
    RTCRtpHeaderExtensionParameters,
)
from .rtcrtpreceiver import RTCRtpReceiver
from .rtcrtpsender import RTCRtpSender
from .sdp import DIRECTIONS

logger = logging.getLogger(__name__)


class RTCRtpTransceiver:
    """
    The RTCRtpTransceiver interface describes a permanent pairing of an
    :class:`RTCRtpSender` and an :class:`RTCRtpReceiver`, along with some
    shared state.
    """

    def __init__(
        self,
        kind: str,
        receiver: RTCRtpReceiver,
        sender: RTCRtpSender,
        direction: str = "sendrecv",
    ):
        self.__currentDirection: Optional[str] = None
        self.__direction = direction
        self.__kind = kind
        self.__mid: Optional[str] = None
        self.__mline_index: Optional[int] = None
        self.__receiver = receiver
        self.__sender = sender
        self.__stopped = False

        self._offerDirection: Optional[str] = None
        self._preferred_codecs: list[RTCRtpCodecCapability] = []

        # FIXME: this is only used by RTCPeerConnection
        self._bundled = False
        self._codecs: list[RTCRtpCodecParameters] = []
        self._headerExtensions: list[RTCRtpHeaderExtensionParameters] = []

    @property
    def currentDirection(self) -> Optional[str]:
        """
        The currently negotiated direction of the transceiver.

        One of `'sendrecv'`, `'sendonly'`, `'recvonly'`, `'inactive'` or `None`.
        """
        pass

    @property
    def direction(self) -> str:
        """
        The preferred direction of the transceiver, which will be used in
        :meth:`RTCPeerConnection.createOffer` and
        :meth:`RTCPeerConnection.createAnswer`.

        One of `'sendrecv'`, `'sendonly'`, `'recvonly'` or `'inactive'`.
        """
        pass

    @direction.setter
    def direction(self, direction: str) -> None:
        pass

    @property
    def kind(self) -> str:
        pass

    @property
    def mid(self) -> Optional[str]:
        pass

    @property
    def receiver(self) -> RTCRtpReceiver:
        """
        The :class:`RTCRtpReceiver` that handles receiving and decoding
        incoming media.
        """
        pass

    @property
    def sender(self) -> RTCRtpSender:
        """
        The :class:`RTCRtpSender` responsible for encoding and sending
        data to the remote peer.
        """
        pass

    @property
    def stopped(self) -> bool:
        pass

    def setCodecPreferences(self, codecs: list[RTCRtpCodecCapability]) -> None:
        """
        Override the default codec preferences.

        See :meth:`RTCRtpSender.getCapabilities` and
        :meth:`RTCRtpReceiver.getCapabilities` for the supported codecs.

        :param codecs: A list of :class:`RTCRtpCodecCapability`, in decreasing order
                        of preference. If empty, restores the default preferences.
        """
        pass

    async def stop(self) -> None:
        """
        Permanently stops the :class:`RTCRtpTransceiver`.
        """
        await self.__receiver.stop()
        await self.__sender.stop()
        self.__stopped = True

    def _setCurrentDirection(self, direction: str) -> None:
        pass

    def _set_mid(self, mid: str) -> None:
        pass

    def _get_mline_index(self) -> Optional[int]:
        pass

    def _set_mline_index(self, idx: int) -> None:
        pass
