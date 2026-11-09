# Creating Podcasts - Turn Research into Audio

Generate an audio episode from your sources and notes. How generation works, and what each setting means, is explained in [Podcasts Explained](../2-CORE-CONCEPTS/podcasts-explained.md).

Podcasts live on the **Podcasts** page (sidebar, under **Create**), which has two tabs: **Episodes** and **Profiles**.

---

## Before Your First Episode: Set Up Profiles

You need at least one **speaker profile** with a voice model and one **episode profile** with an outline and transcript model.

Open **Podcasts → Profiles**. A new install already has three speaker profiles and three episode profiles, but **none of them has models assigned**; they show a **Setup required** badge (upgraded installations may already have models on them). Either edit them or create your own. Create speakers first: episode profiles reference a speaker profile.

You'll need these models added in **Manage → Models** (**Sync Models** → **Discover Models** on a provider configuration); you then select them in the profile fields below:
- a **text-to-speech** model (for voices). Which providers offer TTS is listed in [AI Providers](../4-AI-PROVIDERS/index.md); for a local option see [Local TTS](../5-CONFIGURATION/local-tts.md).
- a **language** model for the outline and transcript.

### Speaker profile

Click **Create speaker** (or **Edit** on an existing one) and fill in:

| Field | Notes |
|-------|-------|
| **Profile name**, **Description** | For you |
| **Voice model** | Required. The TTS model all speakers use by default |
| **Speakers** | One to four. **Add speaker** for more |
| → **Name** | The name used in the script |
| → **Voice ID** | A voice name of the voice model, typed exactly (for example `nova` for OpenAI). Check your TTS provider's voice list |
| → **Backstory**, **Personality** | Who they are and how they talk; the transcript model uses both |
| → **Per-speaker TTS override (optional)** | A different voice model for this speaker, or **Use profile default** |

The seeded profiles use OpenAI voice names (`nova`, `alloy`, ...). If your voice model is from another provider, change the Voice IDs, or generation fails with a voice error.

### Episode profile

Click **Create profile** (or **Edit**) and fill in:

| Field | Notes |
|-------|-------|
| **Profile name**, **Description** | For you |
| **Speaker profile** | Which speakers to use |
| **Outline model**, **Transcript model** | Language models; they can be the same |
| **Segments** | 3 to 20. More segments make a longer episode |
| **Default briefing** | Required. Structure, tone, audience and goals for this format, in plain words. This is where "keep it casual", "aimed at beginners" or "end with open questions" goes |
| **Language** | Optional. The language of the outline and transcript (for example Portuguese (Brazil)). Pick voices that can speak it |
| **Max output tokens** | Optional cap on each generation step (outline, transcript). Blank uses 8192. Set it lower only if your model's output limit is below 8192 |

Profiles can also be **Duplicated** and **Deleted**. A speaker profile that an episode profile uses can't be deleted until you change that episode profile.

---

## Generate an Episode

1. Click **Generate Podcast** on the **Episodes** tab (or use sidebar **New → Podcast**, or **New Podcast** in Quick actions).
2. In **Generate Podcast Episode**, under **Content**, pick what to include. Expand a notebook and select it as a whole, or individual sources and notes. For each source choose:
   - **Summary**: the source's title and insights (small; a source without insights adds almost nothing).
   - **Full content**: title, insights and full text.

   The dialog shows the number of selected items and an estimated token and character count. You can mix content from several notebooks.
3. Under **Episode Settings**:
   - **Episode profile**: required.
   - **Episode name**: required.
   - **Additional instructions**: optional; appended to the profile's briefing for this episode only (for example "focus on the methodology section").
4. Click **Generate**. You'll see *Podcast task started*.

Generation runs in the background worker, so you can close the page. It takes several minutes, depending on the amount of content, the number of segments and your providers. If episodes stay pending, the worker isn't running.

---

## Episodes

The **Episodes** tab groups episodes into **Currently Processing**, **Queued / Pending**, **Completed Episodes** and **Failed Episodes**, with totals at the top.

Each episode card has:
- an **audio player** (completed episodes),
- **Details**, with the episode's **Summary** (profiles and models used), **Outline** and **Transcript**,
- **Publish** / **Unpublish** (completed episodes), which put the episode in your private podcast feed or take it out; see [Listen in a podcast app](#listen-in-a-podcast-app),
- **Delete** (removes the episode and its audio file),
- **Retry** (failed episodes): deletes the failed episode and submits a new job with the same name, content, episode profile and speaker profile, using the profiles' current settings (so you can fix a profile, then retry). The episode's **Additional instructions** are not kept.

Failed episodes show the error. Common errors and fixes are listed in [Podcasts Explained → When Things Go Wrong](../2-CORE-CONCEPTS/podcasts-explained.md#when-things-go-wrong-failures--retry).

---


---

## Listen in a podcast app

Published episodes appear in one private podcast feed that you follow by its link in Apple Podcasts (or any podcast app that can add a show by URL). Nothing is public: only people with the link can listen, and nothing is published until you choose to.

### 1. Give the server an HTTPS address

The feed link needs the secure (`https://`) address that podcast apps use to reach this server. If the **Listen in a podcast app** card on the Podcasts page says *HTTPS address needed*, ask whoever runs your server to set `OPEN_NOTEBOOK_PUBLIC_URL` (see [Environment Reference](../5-CONFIGURATION/environment-reference.md)), for example `https://notebook.example.com`, and restart. Many setups already have a suitable `API_URL`, which is used when `OPEN_NOTEBOOK_PUBLIC_URL` is not set.

### 2. Publish an episode

On a completed episode (Podcasts page or a notebook's Podcasts list) choose **Publish**. A short dialog shows the description podcast apps will display, pre-filled from the episode's outline; edit it if you like. Only completed `.mp3` and `.m4a` episodes can be published, and if something is wrong (a missing audio file, for instance) the reason is shown.

Published episodes show **In your feed** and an **Unpublish** button, which takes the episode out of the feed straight away. Apps that already downloaded it keep their copy. To change the description of a published episode, unpublish and publish again; it then shows up as a new episode.

### 3. Add the show in Apple Podcasts

Copy the link from the **Listen in a podcast app** card, then:

- **iPhone or iPad:** Library, the More (…) menu, **Follow a Show by URL**, paste the link, tap **Follow**.
- **Mac:** File, **Follow a Show by URL**, paste the link, click **Follow**.

The show stays in your own Library and is not added to Apple's public directory. New episodes appear when the app next refreshes the feed.

### 4. Name your show and add cover art

The **About your show** card sets the show title, author, description and language. Blank fields use the defaults. Cover art must be a **square PNG or JPEG between 1400 and 3000 pixels, up to 10 MB**; anything else is refused with the reason.

### Keep the link private

The link contains a secret token and needs no password: anyone who has it can listen to your published episodes (and nothing else in Nova-Notes). If it leaks, choose **Rotate link**. That creates a new link and stops the old one, so every app subscribed with the old link stops updating until you follow the new one.

### If Apple Podcasts cannot load the feed

- The server has to be reachable at the feed's address when the app refreshes. If it is only on a private network (a Tailscale tailnet, for example), the device needs to be able to reach that network at that moment. Check that the link opens in a browser on the same device.
- If the link opens in a browser but Apple Podcasts still cannot load it, the address may need to be reachable from the public internet; that is a server setup decision, not a setting in Nova-Notes.
- A link that stopped working after a rotation needs to be followed again.

---

## Tips for Better Episodes

- **Select less content.** The outline and transcript models read everything you select, every time. *Summary* for background sources and *Full content* for the main ones keeps cost down and focus up.
- **Put the direction in the briefing.** Tone, audience, structure and what to emphasize all come from the default briefing plus the additional instructions; the more concrete, the better.
- **Give speakers distinct personalities and voices.** Two speakers with the same voice and similar personalities are hard to follow.
- **Retry once on odd failures.** Some failures (such as *Invalid speaker name*) come from a single bad model response and succeed on retry.
- **Cost** is the outline and transcript language-model calls (which include all selected content) plus text-to-speech for the full script. Check your providers' pricing.
