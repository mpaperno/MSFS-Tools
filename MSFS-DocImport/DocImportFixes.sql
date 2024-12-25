-- Fix ADF frequency type;  Seems to be fixed in published docs as of Aug 5th, '23.
UPDATE SimVars SET Units = 'Frequency BCD32' WHERE Name = 'ADF ACTIVE FREQUENCY';
-- Fix piston engine category name
UPDATE SimVars SET Category = 'Reciprocal (Piston) Engine' WHERE Category = 'Reciprical (Piston) Engine Vars';
UPDATE KeyEvents SET System = 'Aircraft Autopilot' WHERE System = 'Aircraft Autopilot/Flight Assistance';

-- normalize to lower case
-- there are a few abbreviations and such we don't really want to lower-case, so try to be selective.
UPDATE SimVarUnits
SET Name = lower(substr(Name, 1, 1)) || substr(Name, 2);
UPDATE SimVarUnits
SET ShortName = lower(substr(ShortName, 1, 1)) || substr(ShortName, 2)
WHERE ShortName NOT REGEXP '[KMP].+';
UPDATE SimVarUnits
SET Aliases = lower(Aliases);

-- outliers for lower case normalizing
UPDATE SimVarUnits SET Name = lower(Name),  ShortName = lower(ShortName),  Aliases = lower(Aliases) WHERE lower(Name) LIKE 'g force%';
UPDATE SimVarUnits SET Aliases = lower(Aliases) WHERE Name = 'slugs per cubic feet';
UPDATE SimVarUnits SET Aliases = lower(Aliases) WHERE Name = 'watts';

-- Create new Measure categories for some types which can be grouped but aren't.

-- percentage types: there are 5 of them
UPDATE SimVarUnits SET Measure = 'Percentage' WHERE Name LIKE 'percent%';
-- sound levels: 2 of these
UPDATE SimVarUnits SET Measure = 'Sound Level' WHERE Name LIKE '%bels';

-- 'position' types: there are actually 4 different units in one entry here, break them up into own Measure.
DELETE FROM SimVarUnits WHERE ShortName = 'position';
INSERT INTO SimVarUnits VALUES
('Position', 'position',     'position',     'position,',     'The input value will be converted to an integer position value using the "part" base scale.' ),
('Position', 'position 16k', 'position 16k', 'position 16k,', 'The input value will be converted to an integer position value as a 16 bit integer.'),
('Position', 'position 32k', 'position 32k', 'position 32k,', 'The input value will be converted to an integer position value as a 32bit integer.'),
('Position', 'position 128', 'position 128', 'position 128,', 'The input value will be converted to an integer position value as an integer between 0 and 128.');

-- rename 'numbers' to 'number' as the primary name (outlier to the "plural is best" rule).
UPDATE SimVarUnits SET Name = 'number' WHERE Name = 'numbers'

-- add "integer" alias which isn't documented.
INSERT INTO SimVarUnits VALUES ('Miscellaneous Units', 'integer', 'integer', 'integer', 'The input value is expected to be any integral number.');

-- add "scalar" aliases to "scaler" types (SimVar reference uses "scalar")
UPDATE SimVarUnits SET Aliases = Aliases || 'percent scalar 16k,' WHERE Name = 'percent scaler 16k';
UPDATE SimVarUnits SET Aliases = Aliases || 'percent scalar 32k,' WHERE Name = 'percent scaler 32k';
UPDATE SimVarUnits SET Aliases = Aliases || 'percent scalar 2pow23,' WHERE Name = 'percent scaler 2pow23';
UPDATE SimVarUnits SET Aliases = Aliases || 'celsius scalar 16k,' WHERE Name = 'celsius scaler 16k';
UPDATE SimVarUnits SET Aliases = Aliases || 'celsius scalar 256,' WHERE Name = 'celsius scaler 256';
UPDATE SimVarUnits SET Aliases = Aliases || 'celsius scalar 1/256,' WHERE Name = 'celsius scaler 1/256';
UPDATE SimVarUnits SET Aliases = Aliases || 'meters scalar 256,meter scalar 256,' WHERE Name = 'meters scaler 256';
UPDATE SimVarUnits SET Aliases = Aliases || 'psi scalar 16k,' WHERE Name = 'psi scaler 16k';
UPDATE SimVarUnits SET Aliases = Aliases || 'scalar,' WHERE Name = 'scaler';

-- Add "BCD16" which appears in SimVars list as alias for "Frequency BCD16"
UPDATE SimVarUnits SET Aliases = Aliases || 'BCD16,' WHERE lower(Name) = 'frequency bcd16';

-- Add "Frequency ADF BCD32" alias which appears in SimVars list as alias for "Frequency BCD32", and delete the original Units entry.
UPDATE SimVarUnits SET Aliases = Aliases || 'frequency adf bcd32,' WHERE lower(Name) = 'frequency bcd32';
DELETE * FROM SimVarUnits WHERE lower(Name) = 'frequency adf bcd32';

-- Hz short name missing & aliases extra comma
UPDATE SimVarUnits SET ShortName = 'Hz',  Aliases = 'hertz,hz,' WHERE lower(Name) = 'hertz';

-- newton meters wrong Name and aliases extra comma
UPDATE SimVarUnits SET Name = 'newton meters', Aliases = 'newton meter,newton meters,nm,' WHERE lower(Name) = 'newton meter';

-- "slugs feet" to "slugs per feet"
UPDATE SimVarUnits SET Name = 'slugs per feet squared',  Aliases = Aliases || 'slugs per feet squared,' WHERE Name = 'slugs feet squared';

