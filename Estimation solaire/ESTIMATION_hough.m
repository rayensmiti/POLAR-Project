% ============================================================
% ESTIMATION SOLAIRE PAR HOUGH
% ============================================================
folder_path = uigetdir('', 'Sélectionnez le dossier de session');
if folder_path == 0, disp('Aucun dossier sélectionné.'); return; end

% Chargement du fichier aopl.mat (uniquement)
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

% Offset d'alignement du rail (à adapter selon votre mesure)
AZIMUT_OFFSET = 311.5118;

% Appel de la fonction Hough
[Az_sun_est, ~] = detect_sun_line_hough(aopl_deg, AZIMUT_OFFSET, 5);


% Comparaison avec l'éphéméride si présente
eph_file = fullfile(folder_path, 'ephemeride.json');
if exist(eph_file, 'file')
    fid = fopen(eph_file, 'r'); raw = fread(fid, inf, 'char=>char'); fclose(fid);
    eph = jsondecode(raw');
    az_reel = eph.sun_azimuth_deg;
% --- Correction de 180° (si nécessaire) ---
    diff = mod(Az_sun_est - az_reel + 180, 360) - 180;
    if abs(diff) > 90
        Az_sun_est = mod(Az_sun_est - 180, 360);

    end
    fprintf('Azimut solaire estimé (Hough) : %.2f°\n', Az_sun_est);
    fprintf('--- Éphéméride ---\nAzimut réel : %.2f°\nÉlévation réelle : %.2f°\n', eph.sun_azimuth_deg, eph.sun_elevation_deg);
    fprintf('Erreur azimut : %.2f°\n', abs(Az_sun_est - eph.sun_azimuth_deg));
end    




