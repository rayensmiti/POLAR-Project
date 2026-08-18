function [Azimuth_sun_hat,Elevation_sun_hat,cleanI] = Sun_Estimator_az_eig2(Particle_azimuth_matrix, Particle_elevation_matrix, AOP_median_frame, radius)


%  INPUTS :
%Particle_azimuth_matrix : azimuth (rad) of the particles in sky (matrix) 
%Particle_elevation_matrix : elevation (rad) of the particles in sky (matrix) 
%AOP_median_frame : AOP (rad) in the meridian frame (local frame) preovided by the camera (matrix)
%Gamma_hat : Estimated scattering angle from the DolP provided by the camera (matrix)
%R1 : rotation matrix orientation of the image sensor in the global frame
% Sign : 0 or 1 in order to fix an a-priori orientation of the E-vector in the
% meridian frame

    
%  OUTPUTS :
%Azimuth_sun_hat : Estimated solar azimuth (rad, matrix))
%Elevation_sun_hat : Estimated solar elevation (rad, matrix)


%  MEANING :
%This function takes four inputs:
% Particle matrix is calculated from the macro pixel size, number of macro
% pixel and focal length of the camera provided by the calibration


%This function provides two outputs:
%...

%There is an indetermination in the orientation of the E-vector with
%respect to the solar meriadian
% We used here the sign variable to calculate estimate the sun position 
% from the two possible orientations of the E-vector in the local frame 
%The E vector in the global frame is always perpendicular to the Sun and in
%the local frame perpendicular to the plane POS (particle-observer-sun)

%Estimated Epol_L in local frame
% x = -cos(AOP_median_frame);
% y = sin(AOP_median_frame);
% z = 0;

%OR (depending on Sign value)
% x = cos(AOP_median_frame);
% y = -sin(AOP_median_frame);
% z = 0;

if nargin < 4
    radius = 150;   % valeur par défaut 
end

[m,n] = size(AOP_median_frame);

%Rotation by pi/2 following OpenSky orientation : camera to image frame
eul = [0 0 0];  %tried: pi and pi/2 and 0 the agle between the camera 0 polarization and the x axis of a matrix 66,50° clockwise
R = eul2rotm(eul,"ZXY");

Ep_M = [0;0;0];

%Apply circular mask to AoP
I = mat2gray(AOP_median_frame*180/pi, [0,180]);
cleanI = I;
I = flipud(I);
sz = size(I);

% Create an automatic circular mask
[X, Y] = meshgrid(1:sz(2), 1:sz(1));
centerX = sz(2)/2;
centerY = sz(1)/2;
%radius = 600; % You can adjust the radius if needed

BW = (X - centerX).^2 + (Y - centerY).^2 <= radius^2; % Circle equation

% Apply the mask
BW = flipud(BW);
AOP_median_frame(~BW) = NaN;

for i=1:m
    for j=1:n
          
    Epol_L = [cos(-AOP_median_frame(i,j));sin(-AOP_median_frame(i,j)); 0];
    
    R_theta = [[sin(Particle_elevation_matrix(i,j)) 0 -cos(Particle_elevation_matrix(i,j))];[0 1 0];[cos(Particle_elevation_matrix(i,j)) 0 sin(Particle_elevation_matrix(i,j))]];
    R_alpha = [[cos(Particle_azimuth_matrix(i,j)) sin(Particle_azimuth_matrix(i,j)) 0];[-sin(Particle_azimuth_matrix(i,j)) cos(Particle_azimuth_matrix(i,j)) 0];[0 0 1]];

    R_mat = R*R_theta*R_alpha;
    Ep = -R_mat'*Epol_L;

    Ep_M=horzcat(Ep_M,Ep);
    
    end
end

Ep_M(:,1) = [];
[~, col] = find(isnan(Ep_M));
Ep_M(:,col)=[];

M=Ep_M*Ep_M';
[V,~] = eigs(M,1,'SM');
%V=-V;
[alpha_s_hat,theta_s_hat] = cart2sph(V(1),V(2),V(3));

Azimuth_sun_hat = alpha_s_hat;
Elevation_sun_hat = theta_s_hat;
  
end

