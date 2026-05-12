# Import-readiness overzicht

Gebaseerd op de nieuwste beschikbare dry-run rapporten in `import_reports`. Er is niets geimporteerd; dit is alleen een leesbaar overzicht van de bestaande validatierapporten.

## 1. Korte conclusie

- Bijna klaar voor proefimport: Harderwijk uitjes/evenementen, Lelystad food/drink, Amersfoort uitjes/evenementen, Amersfoort restaurants.
- Bruikbaar maar eerst kort reviewen: Lelystad uitjes/evenementen, omdat dit rapport nog onbekende categorieen en enkele incomplete dates meldt.
- Eerst fouten oplossen: Harderwijk restaurants/food drink. Dit bestand heeft 2 concrete foutregels.
- De meeste overige meldingen zijn waarschuwingen: ontbrekende `image_url`, ontbrekende `price_note`, ontbrekende latitude/longitude, incomplete dates of SourceUrl-waarden die geen volledige URL zijn.

## 2. Status per bestand

| Bestand | Stad | Type | Totaal rijen | Geldige rijen | Rijen met fouten | Rijen met waarschuwingen | Status | Advies |
|---|---|---|---:|---:|---:|---:|---|---|
| harderwijk_uitjes_evenementen_mastertemplate_gecombineerd.xlsx | harderwijk | outings | 84 | 84 | 0 | 84 | Oranje | Bruikbaar, maar review vooral `SourceUrl`-waarden en ontbrekende afbeeldingen. |
| harderwijk_restaurants_food_drink_mastertemplate_gecombineerd.xlsx | harderwijk | food_drink | 89 | 87 | 2 | 87 | Rood | Los eerst de 2 foutregels op; daarna opnieuw dry-runnen. |
| lelystad_uitjes_evenementen_mastertemplate_gecombineerd.xlsx | lelystad | outings | 83 | 83 | 0 | 83 | Oranje | Bruikbaar, maar dit rapport is ouder dan de category-mapping verbetering; opnieuw dry-runnen voor eerlijkere categorie-uitkomst. |
| lelystad_restaurants_food_drink_mastertemplate_gecombineerd.xlsx | lelystad | food_drink | 86 | 86 | 0 | 86 | Oranje | Geen blokkerende fouten; review vooral ontbrekende coordinaten. |
| amersfoort_uitjes_evenementen_mastertemplate_gecombineerd.xlsx | amersfoort | outings | 139 | 139 | 0 | 139 | Oranje | Geen blokkerende fouten; review incomplete dates en ontbrekende coordinaten. |
| amersfoort_restaurants_mastertemplate_gecombineerd.xlsx | amersfoort | food_drink | 54 | 54 | 0 | 54 | Oranje | Geen blokkerende fouten; review vooral ontbrekende coordinaten. Dit rapport is ouder dan de food/date-regelverbetering. |

## 3. Concrete fouten die ik moet oplossen

### harderwijk_restaurants_food_drink_mastertemplate_gecombineerd.xlsx

| Rij | Naam/titel | Fout | Wat aanpassen in Excel |
|---:|---|---|---|
| 38 | Friethuys Majo | `missing required field: source_url` | Vul `SourceUrl` met een bronpagina of betrouwbare website-URL. |
| 55 | Bosrestaurant Het Draakje | `city mismatch: row city 'hierden' does not match --city 'harderwijk'` | Zet `City` op `harderwijk` als dit onder Harderwijk geimporteerd moet worden, of houd dit apart voor latere ondersteuning van plaatsen binnen de gemeente. |

Er zijn geen foutregels in de nieuwste beschikbare rapporten voor de andere bestanden.

## 4. Waarschuwingen die niet direct blokkeren

- Ontbrekende `image_url`: komt veel voor. Dit blokkeert import niet, maar items zien er minder rijk uit in de app.
- Ontbrekende `price_note`: komt veel voor. Dit blokkeert import niet; handig om later aan te vullen voor tickets, horeca of arrangementen.
- Ontbrekende latitude/longitude: blijft belangrijk voor kaartweergave. Dit is geen harde fout, maar review dit vooral bij Lelystad food/drink, Amersfoort uitjes en Amersfoort restaurants.
- Incomplete dates: belangrijk voor uitjes/evenementen. Voor restaurants is dit meestal minder relevant, omdat restaurants vaste plekken zijn.
- `SourceUrl is not a full URL`: de bron is aanwezig, maar lijkt soms een referentie of bronnotitie in plaats van een `https://...` URL. Dit blokkeert niet, maar is het controleren waard.
- Onbekende categorieen in Lelystad uitjes: dit rapport is gemaakt voor de nieuwste category-mapping op alle bestanden opnieuw is toegepast. Draai dit bestand opnieuw door de dry-run validator voordat je hier handmatig veel tijd in steekt.

## 5. Beste volgende stap

Los eerst de 2 foutregels in Harderwijk restaurants op: rij 38 `Friethuys Majo` en rij 55 `Bosrestaurant Het Draakje`. Draai daarna opnieuw een dry-run voor Harderwijk restaurants. Als die rood verdwijnt, begin dan met een proefimport van een klein, overzichtelijk bestand zoals Harderwijk uitjes/evenementen.
