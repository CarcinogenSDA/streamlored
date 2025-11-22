"""OBS WebSocket client for screenshot capture."""

import asyncio
import base64
import hashlib
import json
import logging
import uuid

import websockets

logger = logging.getLogger(__name__)


class OBSWebSocketClient:
    """Client for OBS WebSocket to capture screenshots."""

    def __init__(self, host: str, port: int, password: str = "") -> None:
        """Initialize the OBS WebSocket client.

        Args:
            host: OBS WebSocket host
            port: OBS WebSocket port
            password: OBS WebSocket password (if authentication enabled)
        """
        self.host = host
        self.port = port
        self.password = password
        self._ws = None

    async def connect(self) -> bool:
        """Connect to OBS WebSocket.

        Returns:
            True if connected and authenticated successfully
        """
        try:
            uri = f"ws://{self.host}:{self.port}"
            self._ws = await websockets.connect(uri, max_size=10 * 1024 * 1024)  # 10MB limit

            # Receive Hello message
            hello = json.loads(await self._ws.recv())
            if hello.get("op") != 0:
                logger.error("Expected Hello message from OBS")
                return False

            # Authenticate if required
            auth_data = hello.get("d", {}).get("authentication")
            if auth_data:
                if not self.password:
                    logger.error("OBS requires authentication but no password provided")
                    return False

                # Generate authentication string
                challenge = auth_data.get("challenge", "")
                salt = auth_data.get("salt", "")
                auth_string = self._generate_auth_string(challenge, salt)

                identify = {
                    "op": 1,
                    "d": {
                        "rpcVersion": 1,
                        "authentication": auth_string,
                    }
                }
            else:
                identify = {
                    "op": 1,
                    "d": {
                        "rpcVersion": 1,
                    }
                }

            await self._ws.send(json.dumps(identify))

            # Wait for Identified response
            response = json.loads(await self._ws.recv())
            if response.get("op") != 2:
                logger.error(f"Authentication failed: {response}")
                return False

            logger.info(f"Connected to OBS WebSocket at {uri}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to OBS: {e}")
            return False

    def _generate_auth_string(self, challenge: str, salt: str) -> str:
        """Generate authentication string for OBS WebSocket.

        Args:
            challenge: Challenge from OBS
            salt: Salt from OBS

        Returns:
            Base64 encoded authentication string
        """
        # Create secret from password + salt
        secret_hash = hashlib.sha256((self.password + salt).encode()).digest()
        secret = base64.b64encode(secret_hash).decode()

        # Create auth response from secret + challenge
        auth_hash = hashlib.sha256((secret + challenge).encode()).digest()
        return base64.b64encode(auth_hash).decode()

    async def disconnect(self) -> None:
        """Disconnect from OBS WebSocket."""
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("Disconnected from OBS WebSocket")

    async def get_screenshot(self, source_name: str | None = None, width: int = 672) -> str | None:
        """Capture a screenshot from OBS.

        Args:
            source_name: Optional source name. If None, captures current program output.
            width: Image width (height scales proportionally)

        Returns:
            Base64 encoded PNG image data, or None on failure
        """
        if not self._ws:
            logger.error("Not connected to OBS")
            return None

        try:
            request_id = str(uuid.uuid4())

            if source_name:
                # Get source screenshot
                request = {
                    "op": 6,
                    "d": {
                        "requestType": "GetSourceScreenshot",
                        "requestId": request_id,
                        "requestData": {
                            "sourceName": source_name,
                            "imageFormat": "png",
                            "imageWidth": width,
                        }
                    }
                }
            else:
                # Get current program screenshot
                request = {
                    "op": 6,
                    "d": {
                        "requestType": "GetCurrentProgramScene",
                        "requestId": request_id,
                        "requestData": {}
                    }
                }

                await self._ws.send(json.dumps(request))
                response = json.loads(await self._ws.recv())

                if response.get("op") != 7:
                    logger.error(f"Unexpected response: {response}")
                    return None

                response_data = response.get("d", {}).get("responseData", {})
                current_scene = response_data.get("currentProgramSceneName")

                if not current_scene:
                    logger.error("Could not get current scene name")
                    return None

                # Now get screenshot of that scene
                request_id = str(uuid.uuid4())
                request = {
                    "op": 6,
                    "d": {
                        "requestType": "GetSourceScreenshot",
                        "requestId": request_id,
                        "requestData": {
                            "sourceName": current_scene,
                            "imageFormat": "png",
                            "imageWidth": width,
                        }
                    }
                }

            await self._ws.send(json.dumps(request))

            # Wait for response with timeout
            response = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=10.0))

            if response.get("op") != 7:
                logger.error(f"Unexpected response: {response}")
                return None

            response_data = response.get("d", {})

            # Check for errors
            request_status = response_data.get("requestStatus", {})
            if not request_status.get("result"):
                error_msg = request_status.get("comment", "Unknown error")
                logger.error(f"Screenshot request failed: {error_msg}")
                return None

            # Extract image data (comes as data:image/png;base64,...)
            image_data = response_data.get("responseData", {}).get("imageData", "")

            if not image_data:
                logger.error("No image data in response")
                return None

            # Remove data URI prefix if present
            if image_data.startswith("data:"):
                image_data = image_data.split(",", 1)[1]

            logger.debug(f"Captured screenshot ({len(image_data)} bytes base64)")
            return image_data

        except asyncio.TimeoutError:
            logger.error("Screenshot request timed out")
            return None
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")
            return None

    async def is_connected(self) -> bool:
        """Check if connected to OBS.

        Returns:
            True if connected
        """
        return self._ws is not None and self._ws.open
