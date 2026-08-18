% ============================================================
% COMPARAISON EIGEN vs HOUGH - MULTI-SESSIONS
% ============================================================
clear; close all; clc;

%% 1. Sélection du dossier parent
parent_folder = uigetdir('', 'Sélectionnez le dossier parent contenant les sessions');
if parent_folder == 0
    disp('Aucun dossier sélectionné.');
    return;
end

sessions = dir(parent_folder);
sessions = sessions([sessions.isdir] & ~startsWith({sessions.name}, '.'));
if isempty(sessions)
    error('Aucun sous-dossier trouvé dans le dossier parent.');
end
fprintf('Nombre de sessions trouvées : %d\n', length(sessions));

%% 2. Paramètres fixes
AZIMUT_OFFSET = 311.5118;
RAYON_EIGEN = 150;
EPSILON_HOUGH = 5;

az_real_all = []; az_eig_all = []; az_hough_all = [];
time_all = []; err_eig_all = []; err_hough_all = [];

%% 3. Boucle sur les sessions
for i = 1:length(sessions)
    session_path = fullfile(parent_folder, sessions(i).name);
    fprintf('Session %d/%d : %s\n', i, length(sessions), sessions(i).name);
    
    % Vérification des fichiers
    az_file = fullfile(session_path, 'azimut.mat');
    el_file = fullfile(session_path, 'elevation.mat');
    aopl_file = fullfile(session_path, 'aopl.mat');
    eph_file = fullfile(session_path, 'ephemeride.json');
    if ~exist(az_file,'file') || ~exist(el_file,'file') || ~exist(aopl_file,'file') || ~exist(eph_file,'file')
        fprintf('  Fichiers manquants, ignoré.\n');
        continue;
    end
    
    % Chargement
    az_data = load(az_file);    azimut_deg = az_data.azimut;
    el_data = load(el_file);    elevation_deg = el_data.elevation;
    aopl_data = load(aopl_file);
    if isfield(aopl_data, 'AoPL')
        aopl_deg = aopl_data.AoPL;
    elseif isfield(aopl_data, 'aopl')
        aopl_deg = aopl_data.aopl;
    elseif isfield(aopl_data, 'AOPL')
        aopl_deg = aopl_data.AOPL;
    else
        fprintf('  Variable aopl introuvable, ignoré.\n');
        continue;
    end
    
    % Lecture de l'éphéméride
    fid = fopen(eph_file, 'r');
    raw = fread(fid, inf, 'char=>char');
    fclose(fid);
    eph = jsondecode(raw');
    az_real = eph.sun_azimuth_deg;
    
    % Temps
    t = extract_time(sessions(i).name);
    if isnat(t)
        fprintf('  Format de temps invalide, ignoré.\n');
        continue;
    end
    
    % Préparation des données
    azimut_deg_corr = mod(azimut_deg + AZIMUT_OFFSET, 360);
    azimut_rad = deg2rad(azimut_deg_corr);
    elevation_deg_corr = 90 - elevation_deg;
    elevation_rad = deg2rad(elevation_deg_corr);
    aopl_rad = deg2rad(aopl_deg);
    
    % --- Eigen ---
    [Az_eig_rad, ~, ~] = Sun_Estimator_az_eig2(azimut_rad, elevation_rad, aopl_rad, RAYON_EIGEN);
    az_eig_deg = mod(rad2deg(Az_eig_rad), 360);
    diff = mod(az_eig_deg - az_real + 180, 360) - 180;
    if abs(diff) > 90
        az_eig_deg = mod(az_eig_deg + 180, 360);
    end
    
    % --- Hough ---
    [az_hough_deg, ~] = detect_sun_line_hough(aopl_deg, AZIMUT_OFFSET, EPSILON_HOUGH);
    diff = mod(az_hough_deg - az_real + 180, 360) - 180;
    if abs(diff) > 90
        az_hough_deg = mod(az_hough_deg + 180, 360);
    end
    
    % Stockage
    az_real_all = [az_real_all; az_real];
    az_eig_all = [az_eig_all; az_eig_deg];
    az_hough_all = [az_hough_all; az_hough_deg];
    time_all = [time_all; t];
    err_eig_all = [err_eig_all; az_eig_deg - az_real];
    err_hough_all = [err_hough_all; az_hough_deg - az_real];
end

%% 4. Vérification et tri
if isempty(time_all)
    error('Aucune session valide trouvée.');
end
fprintf('Nombre de sessions valides : %d\n', length(time_all));

[time_all, idx] = sort(time_all);
az_real_all = az_real_all(idx);
az_eig_all = az_eig_all(idx);
az_hough_all = az_hough_all(idx);
err_eig_all = err_eig_all(idx);
err_hough_all = err_hough_all(idx);

%% 5. Métriques
MAE_eig = mean(abs(err_eig_all));
RMSE_eig = sqrt(mean(err_eig_all.^2));
Biais_eig = mean(err_eig_all);

MAE_hough = mean(abs(err_hough_all));
RMSE_hough = sqrt(mean(err_hough_all.^2));
Biais_hough = mean(err_hough_all);

fprintf('\n--- Métriques globales ---\n');
fprintf('Eigen  : MAE = %.2f°, RMSE = %.2f°, Biais = %.2f°\n', MAE_eig, RMSE_eig, Biais_eig);
fprintf('Hough  : MAE = %.2f°, RMSE = %.2f°, Biais = %.2f°\n', MAE_hough, RMSE_hough, Biais_hough);

%% 6. Graphiques
figure('Name', 'Comparaison temporelle Eigen vs Hough', 'Position', [100, 100, 1000, 600]);
hold on;
plot(time_all, az_real_all, 'k-o', 'LineWidth', 2, 'MarkerSize', 5, 'DisplayName', 'Azimut réel');
plot(time_all, az_eig_all, 'b-^', 'LineWidth', 2, 'MarkerSize', 5, 'DisplayName', 'Azimut Eigen');
plot(time_all, az_hough_all, 'r--s', 'LineWidth', 2, 'MarkerSize', 5, 'DisplayName', 'Azimut Hough');
xlabel('Heure locale');
ylabel('Azimut (°)');
grid on;
legend('Location', 'best');
hold off;

figure('Name', 'Erreur instantanée', 'Position', [100, 100, 1000, 400]);
hold on;
plot(time_all, err_eig_all, 'b-^', 'LineWidth', 1.5, 'MarkerSize', 4, 'DisplayName', 'Eigen');
plot(time_all, err_hough_all, 'r--s', 'LineWidth', 1.5, 'MarkerSize', 4, 'DisplayName', 'Hough');
yline(0, 'k--', 'LineWidth', 1.2);
xlabel('Heure locale');
ylabel('Erreur (°)');
ylim([-50 , 30]);
grid on;
legend('Location', 'best');
hold off;

figure('Name', 'Boxplot des erreurs', 'Position', [100, 100, 500, 400]);
boxplot([err_eig_all, err_hough_all], {'Eigen', 'Hough'});
ylabel('Erreur (°)');
grid on;

fprintf('\nFigures sauvegardées dans : %s\n', parent_folder);
fprintf('\n=== FIN ===\n');

% ---------------------------------------------------------
function t = extract_time(folder_name)
    try
        str = strrep(folder_name, 'h', ':');
        str = strrep(str, 'm', ':');
        str = strrep(str, 's', '');
        parts = split(str, '_');
        date_str = parts{1};
        time_str = parts{2};
        t = datetime([date_str ' ' time_str], 'InputFormat', 'dd.MM.yyyy HH:mm:ss');
    catch
        t = NaT;
    end
end