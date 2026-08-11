# Shared integration: France Chorus Pro (B2G) + pointer to B2B PDP

Used by: **[France](../france.md)** for **B2G** (already mandatory).  
French **B2B** (from **2026-09-01**) is **not** “call Chorus Pro for every invoice”: it uses **approved PDPs**. Keep that as a separate future adapter.

## Mandatory?

| Flow | Mandatory now? |
| --- | --- |
| B2G via Chorus Pro | **Yes** (phased 2017–2020, still live) |
| B2B issue/receive via PDP | **Not yet** as of 2026-08-11; **receive all + issue large/mid from 2026-09-01**; SMEs issue **2027-09-01** |

**Local copy (B2B + B2G specs):** [`../_vendor/france-pdp/`](../_vendor/france-pdp/)

- `specifications-externes-v3.2/` — official **v3.2 (2026-04-30)** dossier général, Chorus Pro dossier, semantic annexes, **XSD**, **Swagger/OpenAPI** (directory API)
- `guide_pratique_facturation_electronique.pdf`

This is the public contract for formats, directory (annuaire), e-reporting, and lifecycle. **A given PDP still has its own commercial API** to push/pull invoices; we implement EN 16931 + Flux 1/6 against this pack, then talk to one accredited PDP.

## Official developer sources (Chorus Pro / PISTE)

| Resource | URL |
| --- | --- |
| Chorus Pro community — API OAuth2 | https://communaute.chorus-pro.gouv.fr/documentation/help-for-api-developers-in-oauth2-mode/ |
| Connection modes (EDI / API) | https://communaute.chorus-pro.gouv.fr/documentation/connection-to-chorus-pro/?lang=en |
| PISTE presentation | https://communaute.chorus-pro.gouv.fr/documentation/piste-presentation/?lang=en |
| PISTE / AIFE developer portal | https://developer.aife.economie.gouv.fr/ |
| PISTE registration | https://piste.gouv.fr/en/component/apiportal/registration |
| PISTE user guide | https://developer.aife.economie.gouv.fr/help-center/guide |
| Official AIFE KB | https://portail.chorus-pro.gouv.fr/aife_documentation/ |
| data.gouv API catalog | https://www.data.gouv.fr/dataservices/api-chorus-pro/ |
| Technical account (prod) | https://communaute.chorus-pro.gouv.fr/documentation/creation-of-a-technical-account-for-an-api-access-in-production/ |
| B2B reform (impots) | https://www.impots.gouv.fr/professionnel/je-passe-la-facturation-electronique |

## Chorus Pro API (B2G)

1. Create a PISTE account and application (client id/secret). OAuth 2.0 **replaced** older client-certificate auth — do not follow pre-OAuth guides.
2. Create a Chorus Pro **technical account** and bind it to the PISTE app.
3. `client_credentials` (or the documented grant) against PISTE token endpoint.
4. Call Chorus Pro REST APIs on PISTE with the bearer token (JSON; invoice payload UBL / CII / Factur-X as specified by the current AIFE contract).
5. Qualification (sandbox) vs production are separate PISTE environments.

Always take **path names and schemas** from the live PISTE catalog — AIFE versions the API.

## B2B (from September 2026) — different integration

- Choose a listed **Plateforme de Dématérialisation Partenaire (PDP)**.
- Issue/receive EN 16931 family (UBL, CII, Factur-X) **through that PDP**.
- e-reporting of B2C / some cross-border data rides the same calendar.
- Official list/FAQ: impots.gouv.fr “Je passe à la facturation électronique”.

Do not implement B2B as “upload everything to Chorus Pro”.

## App mapping

- `FR_CHORUS` — B2G only, PISTE OAuth client.
- `FR_PDP` — future B2B, vendor PDP API (not standardised as a single state REST).
