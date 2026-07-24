# Azure Speech Read-Aloud Setup

This guide records the complete setup used to prepare Microsoft Azure Speech for the Writing Tools read-aloud feature. It is intended to make the process repeatable if the resource, subscription, or API key ever needs to be replaced.

**Last verified:** July 24, 2026  
**Project:** Writing Tools  
**Service:** Azure Speech text-to-speech  
**Current resource:** `writingtools-speech`

> **Security warning:** An Azure Speech key is a secret. Never paste it into GitHub, an issue, a chat message, a screenshot, or a committed configuration file. If a key is exposed, regenerate the key in Azure immediately.

## 1. What We Needed

The existing read-aloud options were either unreliable or introduced enough delay that users stopped using them. Azure Speech was selected as a cloud text-to-speech option because it provides natural neural voices and a REST API that can be called directly from the Windows/Linux application.

The minimum Azure pieces required are:

1. A Microsoft account that can sign in to Azure.
2. An active Azure subscription for billing and resource ownership.
3. An Azure Speech resource inside that subscription.
4. The Speech resource key and region.
5. A secure place in Writing Tools to enter the key and region.

The Microsoft Entra ID P1 trial shown during the account screens was **not** the license needed for read-aloud. Entra ID P1 is an identity and access-management product. Azure Speech is the service that generates spoken audio.

## 2. Official Microsoft Links

- [Azure Portal](https://portal.azure.com/)
- [Azure signup and subscription page](https://signup.azure.com/)
- [Create free services with an Azure free account](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/create-free-services)
- [Create an Azure subscription](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/create-subscription)
- [Azure Speech text-to-speech quickstart](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-text-to-speech)
- [Azure Speech text-to-speech REST API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)
- [Azure Speech supported regions](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions)
- [Azure Speech pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/)
- [Azure cost management and billing](https://learn.microsoft.com/en-us/azure/cost-management-billing/)
- [Azure Speech authentication options](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-configure-azure-ad-auth)
- [Azure Speech troubleshooting](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/troubleshooting)

Microsoft may rename portal labels over time. The service may now appear under **Azure AI Speech**, **Speech**, or **Foundry Tools for Speech**, but the resource type is still the Speech service used for text-to-speech.

## 3. Account and Subscription Setup

### 3.1 Sign in to the correct Azure account

1. Open the [Azure Portal](https://portal.azure.com/).
2. Sign in with the Microsoft account that should own the Writing Tools Azure resources.
3. Confirm that the portal shows the expected directory and account in the upper-right account menu.
4. Open **Subscriptions** and check that the subscription is visible.

The subscription used for this project is:

| Setting | Value |
| --- | --- |
| Subscription name | `Azure subscription 1` |
| Subscription ID | `d1f0dd27-ef43-4769-9e22-90591140bdba` |
| Billing model | Pay-As-You-Go |

### 3.2 Why a subscription was necessary

An Azure account and an Azure subscription are related but different:

- The **Microsoft account** is the identity used to sign in.
- The **Azure subscription** is the billing and resource-management boundary.
- The **Speech resource** is the actual service instance used by the application.

The Speech resource could not be created until an eligible subscription existed. When the signup flow displayed **Troubleshoot no eligible subscriptions**, the issue was the subscription/billing state, not the read-aloud code and not an Entra ID license.

### 3.3 Subscription signup and the payment step

The signup flow was opened at [signup.azure.com](https://signup.azure.com/). The signup wizard required account, identity, contact, and billing verification. Payment information was handled in Microsoft’s secure billing flow and was not entered into the Writing Tools project.

If the wizard becomes stuck:

1. Confirm that the correct Microsoft account is signed in.
2. Open **Subscriptions** in the Azure Portal and verify that the new subscription appears.
3. Check the global subscription filter in the portal. A subscription can exist but be hidden by the current filter.
4. Open **Cost Management + Billing** and verify that the billing account and payment method are active.
5. Retry resource creation only after the subscription is visible and active.

Microsoft’s billing documentation notes that a new subscription may not immediately appear if the portal’s global subscription filter is set to another subscription or directory. See [View billing accounts in the Azure portal](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/view-all-accounts).

## 4. Creating the Azure Speech Resource

Once the subscription became available, the resource was created from the Azure Portal.

### 4.1 Open the resource creation page

1. Open the [Azure Portal](https://portal.azure.com/).
2. Select **Create a resource**.
3. Search for **Speech**.
4. Select the Microsoft Azure Speech or Azure AI Speech resource.
5. Select **Create**.

The direct portal route used during setup was:

`https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices`

### 4.2 Values entered in the form

The following values were used:

| Form field | Value | Reason |
| --- | --- | --- |
| Subscription | `Azure subscription 1` | The active project subscription |
| Resource group | `writing-tools-rg` | Keeps Writing Tools resources together |
| Region | `East US` / `eastus` | Must match the application’s configured region |
| Resource name | `writingtools-speech` | Unique name for the Speech resource |
| Pricing tier | `Free F0` | Appropriate for initial testing within Azure’s limits |
| Network access | Public endpoints | Needed for the desktop app to reach Azure directly |
| Identity | None | Not required for key-based desktop testing |

The resource deployment was then submitted and waited on until Azure reported that deployment succeeded.

### 4.3 Important region rule

The region is part of the authentication and endpoint configuration. The app must use the region identifier `eastus` exactly, not the display label `East US` and not a different region. Microsoft documents that Speech keys are region-scoped; using a key with the wrong region can produce authentication errors. See [Supported regions for Azure Speech](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions).

## 5. Retrieving the Speech Key

After deployment, the Azure Portal opened the resource deployment details. The resource can also be opened from **Azure Portal > Resource groups > writing-tools-rg > writingtools-speech**.

To retrieve the key:

1. Open [Azure Portal](https://portal.azure.com/).
2. Open **Resource groups**.
3. Select `writing-tools-rg`.
4. Select `writingtools-speech`.
5. In the resource menu, under **Resource Management**, select **Keys and Endpoint**.
6. Copy **KEY 1** or **KEY 2** using the portal copy button.
7. Keep the key private and do not send it through chat.

The browser was ultimately positioned on the resource’s **Keys and Endpoint** page. The portal route included `.../accounts/writingtools-speech/cskeys`, which confirms that the correct Speech resource key page was reached.

The key page also shows the endpoint and resource region. For this project, the region is `eastus`.

### 5.1 Key rotation

Azure provides two keys so one key can be rotated while the other remains active:

1. Put the new key into Writing Tools.
2. Test read-aloud.
3. Regenerate the old key in Azure.
4. Update any remaining installations that still use the old key.

Do not regenerate a key until all installations using it have been updated.

## 6. Wiring Azure Speech into Writing Tools

The Azure provider was added to the Windows/Linux application.

### 6.1 Files added or changed

- [`Windows_and_Linux/azure_speech.py`](../Windows_and_Linux/azure_speech.py) - REST client for Azure Speech text-to-speech.
- [`Windows_and_Linux/WritingToolApp.py`](../Windows_and_Linux/WritingToolApp.py) - Selects Azure when the Azure provider is chosen and stops playback on cancellation/exit.
- [`Windows_and_Linux/ui/SettingsWindow.py`](../Windows_and_Linux/ui/SettingsWindow.py) - Adds the Azure provider and key/region fields.
- [`Windows_and_Linux/requirements.txt`](../Windows_and_Linux/requirements.txt) - Documents that the implementation uses Python’s standard-library REST client and does not require the Azure Speech SDK.
- [`Windows_and_Linux/version.py`](../Windows_and_Linux/version.py) - Version was bumped to `9.10.0` for the feature.

### 6.2 How the provider works

The app sends SSML text to Azure’s text-to-speech REST endpoint using:

- The resource key in the `Ocp-Apim-Subscription-Key` header.
- The region-specific endpoint for `eastus`.
- Output format `riff-24khz-16bit-mono-pcm`.
- English neural voice `en-US-JennyNeural`.
- Persian neural voice `fa-IR-DilaraNeural`.

The returned PCM/WAV audio is played locally. Text is divided into smaller chunks so a long passage can begin playing without waiting for the entire passage to synthesize. Playback can be cancelled between chunks.

The implementation uses the documented REST API pattern described in [Azure Speech text-to-speech REST API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech).

### 6.3 Entering the key in the application

After copying the key from Azure:

1. Open Writing Tools.
2. Open **Settings**.
3. Open the **General** section.
4. Set the read-aloud provider to **Microsoft Azure Speech**.
5. Paste the key into **Azure Speech resource key**.
6. Enter `eastus` in **Azure Speech region**.
7. Save or close Settings so the configuration is persisted.
8. Select text in Writing Tools and run **Read Aloud**.

The key is stored in the application’s local configuration, which is ignored by Git in this project. It must not be copied into source code, `README.md`, `options.json`, or any committed file.

The provider can also read these environment variables when no key is entered in the application settings:

- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`

For local PowerShell testing, use a process/session value rather than placing the secret in a script committed to the repository:

```powershell
$env:AZURE_SPEECH_KEY = "paste-the-key-locally"
$env:AZURE_SPEECH_REGION = "eastus"
```

Do not include the real value in this document.

## 7. Testing Checklist

Use this checklist after entering the key:

- [ ] The selected provider is **Microsoft Azure Speech**.
- [ ] The region is exactly `eastus`.
- [ ] The key came from the `writingtools-speech` resource’s **Keys and Endpoint** page.
- [ ] A short English selection reads aloud.
- [ ] A longer selection starts playing before the entire passage finishes.
- [ ] Stop/cancel interrupts playback.
- [ ] A second read-aloud request does not overlap the first.
- [ ] Persian text uses the Persian voice when that language is selected or detected.
- [ ] No key appears in logs, screenshots, Git diff, or exception messages.

## 8. Troubleshooting

### Authentication failure, HTTP 401, or HTTP 403

Check all three values:

1. The key belongs to `writingtools-speech`.
2. The region is `eastus`.
3. The resource is active and the key has not been regenerated.

Microsoft’s troubleshooting guidance specifically calls out missing or incorrect Speech keys and regions as common causes. See [Troubleshoot the Speech SDK](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/troubleshooting).

### No eligible subscriptions

This generally means Azure could not find an active subscription eligible for the resource creation flow. Check:

- The subscription is active, not disabled or pending.
- The correct directory/tenant is selected.
- The portal’s subscription filter includes `Azure subscription 1`.
- Billing and payment verification have completed.
- The signed-in account has permission to create resources.

This is a subscription and billing issue, not an Entra ID P1 licensing requirement.

### Resource is not visible

Open **Subscriptions**, change the global subscription filter to `Azure subscription 1`, and then open **Resource groups**. The resource group should be `writing-tools-rg` and the resource should be `writingtools-speech`.

### Audio is slow or does not start

- Test with a short sentence first.
- Confirm the computer has an internet connection.
- Confirm the application is using Azure rather than Local or Word speech.
- Check that the key and region are present in Settings.
- Check for an Azure service or network error in the application log.
- Try a fresh key if the current key was recently regenerated.

Azure still requires a network request for each synthesis chunk. The app reduces perceived delay by chunking text and starting playback as soon as the first chunk is ready; it cannot eliminate network latency entirely.

### Unexpected charges

The resource was created on the Free `F0` tier for testing. Free tiers have usage limits, and Azure billing rules can change. Monitor **Cost Management + Billing**, set a budget alert, and review [Azure Speech pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/) before distributing the feature broadly.

## 9. Current Setup Summary

| Item | Current value |
| --- | --- |
| Azure subscription | `Azure subscription 1` |
| Subscription ID | `d1f0dd27-ef43-4769-9e22-90591140bdba` |
| Resource group | `writing-tools-rg` |
| Speech resource | `writingtools-speech` |
| Region display name | East US |
| Region identifier | `eastus` |
| Pricing tier | Free `F0` |
| Network access | Public |
| Key status | Retrieved from Keys and Endpoint page; keep the value private |
| Application provider | Microsoft Azure Speech |
| App version containing integration | `9.10.0` |

## 10. Recommended Next Step

The Azure account and resource setup is complete. The remaining local step is to paste **KEY 1** into **Writing Tools > Settings > General > Microsoft Azure Speech**, leave the region as `eastus`, save, and run a short read-aloud test. If the key is ever exposed, regenerate it from the same **Keys and Endpoint** page and update the application.
