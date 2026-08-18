% ============================================================
% COMPARAISON JAI vs LUCID (Eigenvalue)
% ============================================================

% Sélection des dossiers parents
disp('Sélectionnez le dossier parent contenant les sessions JAI');
jai_parent = uigetdir('', 'Dossier parent JAI');
if jai_parent == 0, return; end

disp('Sélectionnez le dossier parent contenant les sessions Lucid');
lucid_parent = uigetdir('', 'Dossier parent Lucid');
if lucid_parent == 0, return; end

AZIMUT_OFFSET = 311.5;

az_jai_all = []; az_lucid_all = []; az_real_all = [];
time_jai_all = []; time_lucid_all = [];

%% ----- 1. JAI -----
jai_sessions = dir(jai_parent);
jai_sessions = jai_sessions([jai_sessions.isdir] & ~startsWith({jai_sessions.name}, '.'));

for i = 1:length(jai_sessions)
    session_path = fullfile(jai_parent, jai_sessions(i).name);
    fprintf('JAI : %s\n', jai_sessions(i).name);
    
    az_file = fullfile(session_path, 'azimut.mat');
    el_file = fullfile(session_path, 'elevation.mat');
    aopl_file = fullfile(session_path, 'aopl.mat');
    eph_file = fullfile(session_path, 'ephemeride.json');
    if ~exist(az_file,'file') || ~exist(el_file,'file') || ~exist(aopl_file,'file') || ~exist(eph_file,'file')
        fprintf('  Fichiers manquants, ignoré.\n');
        continue;
    end
    
    azimut_deg = load(az_file); azimut_deg = azimut_deg.azimut;
    elevation_deg = load(el_file); elevation_deg = elevation_deg.elevation;
    aopl_data = load(aopl_file);
    if isfield(aopl_data,'AoPL')
        aopl_deg = aopl_data.AoPL;
    elseif isfield(aopl_data,'aopl')
        aopl_deg = aopl_data.aopl;
    elseif isfield(aopl_data,'AOPL')
        aopl_deg = aopl_data.AOPL;
    else
        fprintf('  Variable aopl introuvable.\n'); continue;
    end
    
    azimut_deg = mod(azimut_deg + AZIMUT_OFFSET, 360);
    elevation_deg = 90 - elevation_deg;
    azimut_rad = deg2rad(azimut_deg);
    elevation_rad = deg2rad(elevation_deg);
    aopl_rad = deg2rad(aopl_deg);
    
    [Az_est, El_est, ~] = Sun_Estimator_az_eig2(azimut_rad, elevation_rad, aopl_rad, 600);
    El_est = -El_est;
    az_jai = mod(rad2deg(Az_est), 360);
    
    fid = fopen(eph_file,'r'); raw = fread(fid,inf,'char=>char'); fclose(fid);
    eph = jsondecode(raw');
    az_real = eph.sun_azimuth_deg;
    
    diff = mod(az_jai - az_real + 180, 360) - 180;
    if abs(diff) > 90
        az_jai = mod(az_jai + 180, 360);
    end
    
    az_jai_all = [az_jai_all; az_jai];
    az_real_all = [az_real_all; az_real];
    t = extract_time(jai_sessions(i).name);
    time_jai_all = [time_jai_all; t];
end

%% ----- 2. Lucid -----
lucid_sessions = dir(lucid_parent);
lucid_sessions = lucid_sessions([lucid_sessions.isdir] & ~startsWith({lucid_sessions.name}, '.'));

for i = 1:length(lucid_sessions)
    session_path = fullfile(lucid_parent, lucid_sessions(i).name);
    fprintf('Lucid : %s\n', lucid_sessions(i).name);
    
    az_file = fullfile(session_path, 'azimut.mat');
    el_file = fullfile(session_path, 'elevation.mat');
    aopl_file = fullfile(session_path, 'aopl.mat');
    eph_file = fullfile(session_path, 'ephemeride.json');
    if ~exist(az_file,'file') || ~exist(el_file,'file') || ~exist(aopl_file,'file') || ~exist(eph_file,'file')
        fprintf('  Fichiers manquants, ignoré.\n');
        continue;
    end
    
    azimut_deg = load(az_file); azimut_deg = azimut_deg.azimut;
    elevation_deg = load(el_file); elevation_deg = elevation_deg.elevation;
    aopl_data = load(aopl_file);
    if isfield(aopl_data,'AoPL')
        aopl_deg = aopl_data.AoPL;
    elseif isfield(aopl_data,'aopl')
        aopl_deg = aopl_data.aopl;
    elseif isfield(aopl_data,'AOPL')
        aopl_deg = aopl_data.AOPL;
    else
        fprintf('  Variable aopl introuvable.\n'); continue;
    end
    
    azimut_deg = mod(azimut_deg + AZIMUT_OFFSET, 360);
    elevation_deg = 90 - elevation_deg;
    azimut_rad = deg2rad(azimut_deg);
    elevation_rad = deg2rad(elevation_deg);
    aopl_rad = deg2rad(aopl_deg);
    
    [Az_est, El_est, ~] = Sun_Estimator_az_eig2(azimut_rad, elevation_rad, aopl_rad, 150);
    El_est = -El_est;
    az_lucid = mod(rad2deg(Az_est), 360);
    
    fid = fopen(eph_file,'r'); raw = fread(fid,inf,'char=>char'); fclose(fid);
    eph = jsondecode(raw');
    az_real = eph.sun_azimuth_deg;
    
    diff = mod(az_lucid - az_real + 180, 360) - 180;
    if abs(diff) > 90
        az_lucid = mod(az_lucid + 180, 360);
    end
    
    az_lucid_all = [az_lucid_all; az_lucid];
    t = extract_time(lucid_sessions(i).name);
    time_lucid_all = [time_lucid_all; t];
end

%% ----- 3. Alignement et graphiques -----
[common_times, idx_jai, idx_lucid] = intersect(time_jai_all, time_lucid_all);
if isempty(common_times)
    error('Aucune session commune trouvée.');
end

az_jai_common = az_jai_all(idx_jai);
az_lucid_common = az_lucid_all(idx_lucid);
az_real_common = az_real_all(idx_jai);

err_jai = az_jai_common - az_real_common;
err_lucid = az_lucid_common - az_real_common;

figure('Name', 'Comparaison JAI vs Lucid (Eigen)', 'Position', [100 100 1000 800]);

subplot(2,1,1);
%yyaxis left;
hold on;
plot(common_times, az_real_common, 'k-o', 'LineWidth', 2, 'MarkerSize', 6, 'DisplayName', 'Azimut réel');
plot(common_times, az_jai_common, 'b-^', 'LineWidth', 2, 'MarkerSize', 6, 'DisplayName', 'JAI');
plot(common_times, az_lucid_common, 'r--s', 'LineWidth', 2, 'MarkerSize', 6, 'DisplayName', 'Lucid');
xlabel('Heure locale');
ylabel('Azimut (°)');


yyaxis right;

% Création des données horaires de température (pour la journée du 22/07/2026)
date_base = datetime(2026, 7, 22, 8, 0, 0);
time_hourly = date_base + hours(0:10);  % 8h à 18h
temp_hourly = [24.0, 25.2, 27.2, 28.9, 30.6, 31.0, 32.0, 31.8, 31.4, 32.1, 32.2];

% Interpolation linéaire aux instants des acquisitions
temp_interp = interp1(time_hourly, temp_hourly, common_times, 'linear');

% Tracé de la température
plot(common_times, temp_interp, 'g-*', 'LineWidth', 1.5, 'MarkerSize', 6, 'DisplayName', 'Température');
ylabel('Température (°C)');


grid on;

ax = gca;
ax.YColor = 'g';          % Couleur de l'axe droit en vert
ax.YAxis(1).Color = 'k';  % Couleur de l'axe gauche en noir (par défaut)

legend('Location', 'best');
hold off;

subplot(2,1,2);
boxplot([err_jai, err_lucid], {'JAI', 'Lucid'});
ylabel('Erreur (°)');
grid on;
yline(0, 'k--', 'LineWidth', 1.2);

% Métriques
biais_jai = mean(err_jai);
biais_lucid = mean(err_lucid);
mae_jai = mean(abs(err_jai));
mae_lucid = mean(abs(err_lucid));
rmse_jai = sqrt(mean(err_jai.^2));
rmse_lucid = sqrt(mean(err_lucid.^2));

fprintf('\n--- Résultats JAI ---\n');
fprintf('Biais : %.2f°\nMAE   : %.2f°\nRMSE  : %.2f°\n', biais_jai, mae_jai, rmse_jai);
fprintf('\n--- Résultats Lucid ---\n');
fprintf('Biais : %.2f°\nMAE   : %.2f°\nRMSE  : %.2f°\n', biais_lucid, mae_lucid, rmse_lucid);

%% Tests statistiques

fprintf('\nTESTS STATISTIQUES (JAI vs LUCID)\n');
n_sessions = length(err_jai);
fprintf('Nombre de sessions communes : %d\n', n_sessions);

if n_sessions < 7
    % Petit échantillon : Mann-Whitney (non paramétrique)
    [p, h] = ranksum(err_jai, err_lucid);
    test_name = 'Mann-Whitney (non paramétrique)';
    fprintf('Test utilisé : %s\n', test_name);
    fprintf('p = %.4f\n', p);
    if p < 0.05
        fprintf('Différence significative (p < 0.05)\n');
        if mean(err_jai) < mean(err_lucid)
            fprintf(' JAI est significativement meilleure.\n');
        else
            fprintf(' Lucid est significativement meilleure.\n');
        end
    else
        fprintf('Pas de différence significative (p >= 0.05)\n');
        fprintf(' Les caméras sont équivalentes.\n');
    end
else
    % Grand échantillon : vérifier normalité et variances
    % Test de normalité (Lilliefors)
    [h_norm_jai, p_norm_jai] = lillietest(err_jai);
    [h_norm_lucid, p_norm_lucid] = lillietest(err_lucid);
    fprintf('Normalité JAI  : p = %.4f\n', p_norm_jai);
    fprintf('Normalité Lucid : p = %.4f\n', p_norm_lucid);
    % Test d'homogénéité des variances (Fisher)
    [h_var, p_var] = vartest2(err_jai, err_lucid);
    fprintf('Homogénéité des variances : p = %.4f\n', p_var);
    
    if h_norm_jai == 0 && h_norm_lucid == 0
        % Les deux sont normales : test paramétrique
        if h_var == 0
            % Variances égales : Student
            [h, p] = ttest2(err_jai, err_lucid, 'Vartype', 'equal');
            test_name = 'Test de Student (variances égales)';
        else
            % Variances inégales : Welch
            [h, p] = ttest2(err_jai, err_lucid, 'Vartype', 'unequal');
            test_name = 'Test de Welch (variances inégales)';
        end
    else
        % Au moins une des deux n'est pas normale : Mann-Whitney
        [p, h] = ranksum(err_jai, err_lucid);
        test_name = 'Mann-Whitney (non paramétrique)';
    end
    
    fprintf('Test utilisé : %s\n', test_name);
    fprintf('p = %.4f\n', p);
    if p < 0.05
        fprintf('Différence significative (p < 0.05)\n');
        if mean(err_jai) < mean(err_lucid)
            fprintf(' JAI est significativement meilleure.\n');
        else
            fprintf(' Lucid est significativement meilleure.\n');
        end
    else
        fprintf('Pas de différence significative (p >= 0.05)\n');
        fprintf('  Les caméras sont équivalentes.\n');
    end
end

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