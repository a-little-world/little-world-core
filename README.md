# Little World Core

An open-source matching platform.

This repository contains all backend code for Little World Software Core. Combined with our other open-source repositories, it provides everything needed to host a fully functional matching platform with live messaging and video calls.

The same platform powers all processes at Little World — [join us and sign up now for cool conversations](https://little-world.com/sign-up)!

---

## Video calls (LiveKit — local)

Video calls run on a [LiveKit](https://livekit.io) server. For local development one runs in Docker.

**Start it** (part of the `all` profile, or on its own):

```bash
docker compose --profile livekit up   # just LiveKit
docker compose --profile all up        # everything, including LiveKit
```

**Ports** (published by the `livekit` service in `docker-compose.yaml`):

| Port | Purpose |
|------|---------|
| `7880` | signaling (WebSocket) |
| `7881/tcp` | ICE/TCP fallback |
| `7882/udp` | media (audio/video) |

**Config** lives in `dev/livekit.yaml`. The `keys:` map (`APIKEY: SECRET`) must match the backend env in `dev/envs/dev.env`:

| `livekit.yaml` | `dev.env` |
|----------------|-----------|
| key name in `keys:` | `DJ_LIVEKIT_API_KEY` |
| its secret in `keys:` | `DJ_LIVEKIT_API_SECRET` |
| secret of `webhook.api_key` | `DJ_LIVEKIT_WEBHOOK_SECRET` |

The backend uses **two** URLs, which differ only in local Docker:

- `DJ_LIVEKIT_URL` (`ws://localhost:7880`) — handed to the browser/app client as the server URL.
- `DJ_LIVEKIT_INTERNAL_URL` (`http://livekit:7880`) — used backend→LiveKit for API calls over the Docker network.

> Testing on a real phone needs TLS (`wss`) and a media path reachable from the device, so `localhost` won't work — you'll need to expose LiveKit on a routable host.

---

## License

Copyright (C) 2025 A Little World gUG

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General Public License version 3 as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the [GNU Lesser General Public License](LICENSE.md) for more details.

You should have received a copy of the GNU Lesser General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

---

## Contributors

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/tbscode"><img src="https://avatars.githubusercontent.com/u/25325944?v=4?s=64" width="64px;" alt="Tim Schupp"/><br /><sub><b>Tim Schupp</b></sub></a><br /><a href="https://github.com/a-little-world/little-world-backend/commits?author=tbscode" title="Code">💻</a> <a href="https://github.com/a-little-world/little-world-backend/commits?author=tbscode" title="Documentation">📖</a> <a href="https://github.com/a-little-world/little-world-backend/issues?q=author%3Atbscode" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Simba14"><img src="https://avatars.githubusercontent.com/u/16307049?v=4?s=64" width="64px;" alt="Sean Blundell"/><br /><sub><b>Sean Blundell</b></sub></a><br /><a href="https://github.com/a-little-world/little-world-backend/commits?author=Simba14" title="Code">💻</a> <a href="https://github.com/a-little-world/little-world-backend/commits?author=Simba14" title="Documentation">📖</a> <a href="https://github.com/a-little-world/little-world-backend/issues?q=author%3ASimba14" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/JannisToelle"><img src="https://avatars.githubusercontent.com/u/52223020?v=4?s=64" width="64px;" alt="JannisToelle"/><br /><sub><b>JannisToelle</b></sub></a><br /><a href="https://github.com/a-little-world/little-world-backend/commits?author=JannisToelle" title="Code">💻</a> <a href="https://github.com/a-little-world/little-world-backend/commits?author=JannisToelle" title="Documentation">📖</a> <a href="https://github.com/a-little-world/little-world-backend/issues?q=author%3AJannisToelle" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/sungsoo-ACN"><img src="https://avatars.githubusercontent.com/u/246235994?v=4?s=64" width="64px;" alt="sungsoo-ACN"/><br /><sub><b>sungsoo-ACN</b></sub></a><br /><a href="https://github.com/a-little-world/little-world-backend/commits?author=sungsoo-ACN" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Hapyr"><img src="https://avatars.githubusercontent.com/u/23398802?v=4?s=64" width="64px;" alt="Jakob Gebler"/><br /><sub><b>Jakob Gebler</b></sub></a><br /><a href="https://github.com/a-little-world/little-world-backend/commits?author=Hapyr" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Stinkiwinki1"><img src="https://avatars.githubusercontent.com/u/104495427?v=4?s=64" width="64px;" alt="Stinkiwinki1"/><br /><sub><b>Stinkiwinki1</b></sub></a><br /><a href="https://github.com/a-little-world/little-world-backend/commits?author=Stinkiwinki1" title="Documentation">📖</a> <a href="https://github.com/a-little-world/little-world-backend/issues?q=author%3AStinkiwinki1" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/akashdeepchoudhury"><img src="https://avatars.githubusercontent.com/u/147383307?v=4?s=64" width="64px;" alt="akashdeepchoudhury"/><br /><sub><b>akashdeepchoudhury</b></sub></a><br /><a href="https://github.com/a-little-world/little-world-backend/commits?author=akashdeepchoudhury" title="Code">💻</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/ConstantinHaag"><img src="https://avatars.githubusercontent.com/u/155448307?v=4?s=64" width="64px;" alt="ConstantinHaag"/><br /><sub><b>ConstantinHaag</b></sub></a><br /><a href="https://github.com/a-little-world/little-world-backend/commits?author=ConstantinHaag" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

<sub>Contributors must sign our [Contributor License Agreement (CLA)](dev/CLA.md) before contributions can be accepted.</sub>

---

**Looking for the internal developer documentation? [It moved here](https://github.com/a-little-world/little-world-backend-docs)**
If you want to contribute we will happily invite you to our development repos, they also contain ephemeral environments and ci-tests.
