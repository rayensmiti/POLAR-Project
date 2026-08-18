function [Az_sun_est, line_angle] = detect_sun_line_hough(aopl_deg, AZIMUT_OFFSET, epsilon_deg)
% detect_sun_line_hough : Estime l'azimut solaire par Hough sur les pixels
% dont l'AoP est proche de 90° (ou -90°).
%
% Entrées :
%   aopl_deg       - matrice 2D de l'AoPL (degrés, 0-180)
%   AZIMUT_OFFSET  - angle de l'axe X de la caméra par rapport au Nord (°)
%   epsilon_deg    - demi‑largeur de la bande autour de 90° (défaut 5°)
%
% Sorties :
%   Az_sun_est     - azimut solaire estimé (degrés, 0-360)
%   line_angle     - angle de la ligne détectée / horizontale (degrés)

    if nargin < 3
        epsilon_deg = 5;   % tolérance de ±5° autour de 90°
    end

    % 1. Convertir l'AoPL en radians pour appliquer le masque
    aopl_rad = deg2rad(aopl_deg);
    epsilon_rad = deg2rad(epsilon_deg);

    % 2. Créer une image binaire : 1 si l'AoP est proche de ±90°, 0 sinon
    target_angle = pi/2;  
    bw = (abs(aopl_rad - target_angle) < epsilon_rad) | ...
         (abs(aopl_rad - (target_angle + pi)) < epsilon_rad);

    % 3. Dilater pour relier les points proches (comme le collègue)
    se = strel('line', 5, 90);   % élément vertical (car la ligne est à peu près verticale)
    bw_dilated = imdilate(bw, se);

    % 4. Transformée de Hough sur l'image binaire dilatée
    [H, theta, rho] = hough(bw_dilated);
    peaks = houghpeaks(H, 1);               % pic le plus fort
    theta_peak = theta(peaks(2));  % angle de la normale (0..180°)
    line_angle = theta_peak;


    % 6. Azimut solaire (0..360°) – le soleil est perpendiculaire à la ligne
    
    %Az_sun_est = mod(Az_camera + AZIMUT_OFFSET + 90, 360)
    Az_sun_est = mod(theta_peak + AZIMUT_OFFSET+90, 360);

    % 7. Affichage (optionnel)
    figure;
    imagesc(aopl_deg); colormap(gray); colorbar;
    title('Azimut estimé (Hough)');
    hold on;

    % Tracer la ligne détectée
    [rows, cols] = size(aopl_deg);
    rho_peak = rho(peaks(1));
    x0 = 1; x1 = cols;
    if abs(cosd(theta_peak)) > 1e-6
        y0 = (rho_peak - x0*cosd(theta_peak)) / sind(theta_peak);
        y1 = (rho_peak - x1*cosd(theta_peak)) / sind(theta_peak);
    else
        y0 = 1; y1 = rows;
    end
    plot([x0 x1], [y0 y1], 'r-', 'LineWidth', 2);
    hold off;
end