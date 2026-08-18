% ESTIMATION SOLAIRE POUR UN DOSSIER DE SESSION

folder_path = uigetdir('', 'Sélectionnez le dossier de session');
if folder_path == 0, disp('Aucun dossier sélectionné.'); return; end

azimut_deg   = load(fullfile(folder_path, 'azimut.mat'));   azimut_deg = azimut_deg.azimut;
elevation_deg= load(fullfile(folder_path, 'elevation.mat')); elevation_deg = elevation_deg.elevation;

% Chargement adaptatif de aopl
aopl_data = load(fullfile(folder_path, 'aopl.mat'));
if isfield(aopl_data, 'AOPL')
    aopl_deg = aopl_data.AOPL;
elseif isfield(aopl_data, 'aopl')
    aopl_deg = aopl_data.aopl;
elseif isfield(aopl_data, 'AoPL')
    aopl_deg = aopl_data.AoPL;
else
    error('Variable aopl, AoPL ou AOPL introuvable dans aopl.mat');
end

% Offset et conversion

AZIMUT_OFFSET = 311.5118;
azimut_geo_deg = mod(azimut_deg + AZIMUT_OFFSET, 360);
azimut_rad = deg2rad(azimut_geo_deg);
elevation_deg = 90 - elevation_deg;    
elevation_rad = deg2rad(elevation_deg);
%aopl_deg = mod(aopl_deg + 90, 180);
aopl_rad = deg2rad(aopl_deg);

% Estimation (rayon du masque = 150)
[Az_sun_est, El_sun_est, cleanI] = Sun_Estimator_az_eig2(azimut_rad, elevation_rad, aopl_rad, 150);
El_sun_est = El_sun_est;   % inversion du signe

if Az_sun_est < 0
    Az_sun_est = mod(Az_sun_est + pi, 2*pi);
end
if El_sun_est < 0
    El_sun_est = -El_sun_est;
end

%fprintf('Azimut solaire estimé   : %.2f°\n', rad2deg(Az_sun_est));
%fprintf('Élévation solaire estimée : %.2f°\n', rad2deg(El_sun_est));

% Comparaison avec l'éphéméride si présente
eph_file = fullfile(folder_path, 'ephemeride.json');
if exist(eph_file, 'file')
    fid = fopen(eph_file, 'r'); raw = fread(fid, inf, 'char=>char'); fclose(fid);
    eph = jsondecode(raw');

    % Correction de l'ambiguïté de 180° si écart > 90°
    az_eph_rad = deg2rad(eph.sun_azimuth_deg);
    % Différence circulaire entre -π et π
    diff = mod(Az_sun_est - az_eph_rad + pi, 2*pi) - pi;
    if abs(diff) > pi/2
        Az_sun_est = mod(Az_sun_est + pi, 2*pi);
    end
    fprintf('Azimut solaire estimé   : %.2f°\n', rad2deg(Az_sun_est));
    fprintf('Élévation solaire estimée : %.2f°\n', rad2deg(El_sun_est));
    fprintf('--- Éphéméride ---\nAzimut réel : %.2f°\nÉlévation réelle : %.2f°\n', eph.sun_azimuth_deg, eph.sun_elevation_deg);
    fprintf('Erreur azimut : %.2f°\nErreur élévation : %.2f°\n', ...
        abs(rad2deg(Az_sun_est)-eph.sun_azimuth_deg), abs(rad2deg(El_sun_est)-eph.sun_elevation_deg));
end

imwrite(cleanI, fullfile(folder_path, 'cleanI_estimated.png'));