# Shared integration: Spain SIF / VERI*FACTU (AEAT)

Used by: **[Spain](../spain.md)**. In-repo product notes: [../sif.md](../../sif.md).

## Mandatory?

**Not yet for SIF/VERI\*FACTU** (legal adaptation: corporate **2027-01-01**, others **2027-07-01**).  
**Yes for B2G** via FACe (see below).  
**Yes for SII** (Immediate Supply of Information) for *in-scope* taxpayers (large, REDEME, etc.) — a **different** AEAT feed.

Implement SIF now as a foundation; do not treat it as a live production duty for every Spanish issuer.

**Local copy:** [`../_vendor/spain-sif/`](../_vendor/spain-sif/) — manuals, hash/QR/validation/FAQ PDFs, and `tikeV1.0/` WSDL+XSD.

## Official developer sources (SIF / VERI*FACTU)

| Resource | URL |
| --- | --- |
| AEAT SIF / VERI\*FACTU | https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html |
| Technical index | https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/informacion-tecnica.html |
| Web-service manual | https://sede.agenciatributaria.gob.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_Descripcion_SWeb.pdf |
| WSDL test | https://prewww2.aeat.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/SistemaFacturacion.wsdl |
| WSDL prod | https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/SistemaFacturacion.wsdl |
| XSD (common / supply / response / events) | same `tikeV1.0/cont/ws/` tree (`SuministroInformacion.xsd`, `SuministroLR.xsd`, `RespuestaSuministro.xsd`, `EventosSIF.xsd`, …) |
| Hash spec | https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_especificaciones_huella_hash_registros.pdf |
| QR spec | https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/DetalleEspecificacTecnCodigoQRfactura.pdf |
| Validations/errors | https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Validaciones_Errores_Veri-Factu.pdf |
| RD 1007/2023 | https://www.boe.es/buscar/act.php?id=BOE-A-2023-24840 |
| Orden HAC/1177/2024 | https://www.boe.es/buscar/act.php?id=BOE-A-2024-22138 |

## Integration shape

- **SOAP**, not REST. Version path `tikeV1.0`.
- Build `RegistroAlta` / `RegistroAnulacion` XML against XSDs; SHA-256 hash per AEAT field order; optional XAdES if **NO_VERI\*FACTU**.
- VERI\*FACTU: continuous, ordered remittance; persist AEAT states / id-peticion.
- Dual mode is required in this product (`VERI_FACTU` | `NO_VERI_FACTU`).

Repo work: #148 settings done; #149–#158 not done. Do not start from KSeF OpenAPI.

## B2G (already mandatory): FACe

| Resource | URL |
| --- | --- |
| FACe | https://face.gob.es/ |
| Facturae format | referenced from FACe / [facturae.gob.es](https://www.facturae.gob.es/) |

FACe is **not** SIF. Optional later `ES_FACE` sender if we invoice Spanish public bodies.

## SII (already mandatory for some issuers)

SII is near-real-time VAT book reporting to AEAT (separate XML). Only implement `ES_SII` if an issuer is in SII scope. Do not conflate with VERI\*FACTU.
