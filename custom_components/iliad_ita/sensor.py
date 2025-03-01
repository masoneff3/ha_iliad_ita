import logging
import requests
import re
import voluptuous as vol
import random
from bs4 import BeautifulSoup
from datetime import timedelta
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=6, minutes=random.randint(0, 15))

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


def setup_platform(hass: HomeAssistant, config, add_entities, discovery_info=None):
    """Set up the Iliad sensors with a shared DataUpdateCoordinator."""
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]

    coordinator = IliadDataCoordinator(hass, username, password)

    add_entities([
        IliadBalanceSensor(coordinator),
        IliadDataUsageSensor(coordinator),
        IliadRemainingDataSensor(coordinator)
    ], True)


class IliadDataCoordinator(DataUpdateCoordinator):
    """Coordinator to manage API calls for Iliad sensors."""

    def __init__(self, hass, username, password):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="iliad_data",
            update_interval=SCAN_INTERVAL
        )
        self._username = username
        self._password = password
        self._session = requests.Session()
        self.data = {}

    def fetch_data(self):
        """Fetch data from iliad.it."""
        try:
            login_url = 'https://www.iliad.it/account/login'
            login_data = {
                'login-ident': self._username,
                'login-pwd': self._password,
            }
            response = self._session.post(login_url, data=login_data)

            if response.status_code != 200:
                _LOGGER.error("Failed to login to Iliad account. Status code: %s", response.status_code)
                return None

            balance_url = 'https://www.iliad.it/account/consumi-e-credito'
            response = self._session.get(balance_url)

            if response.status_code != 200:
                _LOGGER.error("Failed to retrieve Iliad account page. Status code: %s", response.status_code)
                return None

            _LOGGER.info("Fetched most recent data")

            return response.text

        except Exception as e:
            _LOGGER.error("Error fetching Iliad data: %s", e)
            return None

    def parse_data(self, html):
        """Parse the account page to extract balance, data usage, and remaining data."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract balance
        balance_match = re.search(r'<b class="red" data-cs-mask>([\d,.]+)€</b>', html)
        balance = balance_match.group(1) if balance_match else None

        # Extract data usage
        size_pattern = re.compile(r"(\d+[\.,]?\d*)\s?(KB|MB|GB|TB)", re.IGNORECASE)
        data_usage = None
        data_usage_unit = None
        for span in soup.find_all('span', class_='red'):
            match = size_pattern.search(span.text)
            if match:
                data_usage = match.group(1).replace(',', '.')
                data_usage_unit = match.group(2)
                break

        # Extract remaining data
        remaining_value = soup.find('span', class_='big red')
        remaining_unit = soup.find('span', class_='small red')
        remaining_data = remaining_value.text.strip().replace(',', '.') if remaining_value else None
        remaining_data_unit = remaining_unit.text.strip() if remaining_unit else None

        self.data = {
            "balance": balance,
            "data_usage": data_usage,
            "data_usage_unit": data_usage_unit,
            "remaining_data": remaining_data,
            "remaining_data_unit": remaining_data_unit
        }

        _LOGGER.info("Sensors updated")

    async def _async_update_data(self):
        """Fetch and update sensor data asynchronously."""
        html = await self.hass.async_add_executor_job(self.fetch_data)
        if html:
            self.parse_data(html)
        return self.data


class IliadBaseSensor(CoordinatorEntity, Entity):
    """Base class for Iliad sensors."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)

    @property
    def should_poll(self):
        """Disable polling because coordinator handles updates."""
        return False


class IliadBalanceSensor(IliadBaseSensor):
    """Sensor for balance."""

    @property
    def name(self):
        return "Iliad Balance"

    @property
    def state(self):
        return self.coordinator.data.get("balance")

    @property
    def unit_of_measurement(self):
        return "EUR"

    @property
    def icon(self):
        return "mdi:currency-eur"


class IliadDataUsageSensor(IliadBaseSensor):
    """Sensor for data usage."""

    @property
    def name(self):
        return "Iliad Data Usage"

    @property
    def state(self):
        return self.coordinator.data.get("data_usage")

    @property
    def unit_of_measurement(self):
        return self.coordinator.data.get("data_usage_unit")

    @property
    def icon(self):
        return "mdi:progress-download"


class IliadRemainingDataSensor(IliadBaseSensor):
    """Sensor for remaining data."""

    @property
    def name(self):
        return "Iliad Remaining Data"

    @property
    def state(self):
        return self.coordinator.data.get("remaining_data")

    @property
    def unit_of_measurement(self):
        return self.coordinator.data.get("remaining_data_unit")

    @property
    def icon(self):
        return "mdi:progress-check"
