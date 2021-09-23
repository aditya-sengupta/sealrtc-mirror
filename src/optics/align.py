# authored by Benjamin Gerard and Aditya Sengupta

import numpy as np
import time
from matplotlib import pyplot as plt
# import pysao
from scipy.ndimage.filters import median_filter

from ..utils import joindata
from .image import optics
from .tt import mtfgrid, sidemaskrad, sidemaskind
from .ao import mtf, remove_piston
from .tt import applytiptilt, tip, tilt

def align_fast(view=True):
	expt_init = optics.get_expt()
	optics.set_expt(1e-4)

	bestflat = np.load(joindata(os.path.join("bestflats", "bestflat_{0}_{1}.npy".format(optics.name, optics.dmdims[0]))))

	#side lobe mask where there is no signal to measure SNR
	xnoise,ynoise=161.66,252.22
	sidemaskrhon=np.sqrt((mtfgrid[0]-ynoise)**2+(mtfgrid[1]-xnoise)**2)
	sidemaskn=np.zeros(optics.imdims)
	sidemaskindn=np.where(sidemaskrhon<sidemaskrad)
	sidemaskn[sidemaskindn]=1

	def processimabs(imin,mask): #process SCC image, isolating the sidelobe in the FFT and IFFT back to the image
		otf = np.fft.fftshift(np.fft.fft2(imin,norm='ortho')) #(1) FFT the image
		otf_masked = otf * mask #(2) multiply by binary mask to isolate side lobe or noise mask
		Iminus = np.fft.ifft2(otf_masked,norm='ortho') #(3) IFFT back to the image plane, now generating a complex-valued image
		return np.abs(Iminus)

	def optt(tsleep): #function to optimize how long to wait in between applying DM command and recording image
		# ds9 = pysao.ds9()
		applytiptilt(-0.1,-0.1)
		time.sleep(tsleep)
		im1 = optics.stack(10)
		optics.applydmc(bestflat)
		time.sleep(tsleep)
		imf = optics.stack(10)
		return imf
		# ds9.view(im1-imf)
	#tsleep=0.005 #on really good days
	tsleep=0.01 #optimized from above function
	#tsleep=0.4 #on bad days


	cenmaskrho=np.sqrt((mtfgrid[0]-mtfgrid[0].shape[0]/2)**2+(mtfgrid[1]-mtfgrid[0].shape[0]/2)**2) #radial grid for central MTF lobe
	cenmask = np.zeros(optics.imdims)
	cenmaskradmax,cenmaskradmin=49,10 #mask radii for central lobe, ignoring central part where the pinhole PSF is (if not ignored, this would bias the alignment algorithm)   
	cenmaskind=np.where(np.logical_and(cenmaskrho<cenmaskradmax,cenmaskrho>cenmaskradmin))
	cenmask[cenmaskind]=1

	#grid tip/tilt search 
	namp=10
	amparr=np.linspace(-0.1,0.1,namp) 
	# note the range of this grid search is can be small, assuming day to day drifts are minimal 
	# and so you don't need to search far from the previous day to find the new optimal alignment; 
	# for larger offsets the range may need to be increases (manimum search range is -1 to 1); 
	# but, without spanning the full -1 to 1 range this requires manual tuning of the limits 
	# to ensure that the minimum is not at the edge
	ttoptarr=np.zeros((namp,namp))
	for i in range(namp):
		for j in range(namp):
			applytiptilt(amparr[i],amparr[j])
			time.sleep(tsleep)
			imopt = optics.stack(10)
			mtfopt=mtf(imopt)
			sidefraction=np.sum(mtfopt[sidemaskind])/np.sum(mtfopt)
			cenfraction=np.sum(mtfopt[cenmaskind])/np.sum(mtfopt)
			ttoptarr[i,j]=sidefraction+0.1/cenfraction 
			# the factor of 0.01 is a relative weight; because we only expect the fringe visibility to max out at 1%, 
			# this attempts to give equal weight to both terms 

	medttoptarr=median_filter(ttoptarr,3) #smooth out hot pixels, attenuating noise issues
	indopttip,indopttilt=np.where(medttoptarr==np.max(medttoptarr))
	indopttip,indopttilt=indopttip[0],indopttilt[0]
	applytiptilt(amparr[indopttip],amparr[indopttilt])

	if view:
		plt.imshow(medttoptarr)
		plt.show()

	#expt(1e-4)

	ampdiff=amparr[2]-amparr[0] #how many discretized points to zoom in to from the previous iteration
	tipamparr=np.linspace(amparr[indopttip]-ampdiff,amparr[indopttip]+ampdiff,namp)
	tiltamparr=np.linspace(amparr[indopttilt]-ampdiff,amparr[indopttilt]+ampdiff,namp)
	ttoptarr1=np.zeros((namp,namp))
	for i in range(namp):
		for j in range(namp):
			applytiptilt(tipamparr[i],tiltamparr[j])
			time.sleep(tsleep)
			imopt = optics.stack(10)
			mtfopt=mtf(imopt)
			sidefraction=np.sum(mtfopt[sidemaskind])/np.sum(mtfopt)
			cenfraction=np.sum(mtfopt[cenmaskind])/np.sum(mtfopt)
			ttoptarr1[i,j]=sidefraction+0.1/cenfraction 

	medttoptarr1 = median_filter(ttoptarr1,3) #smooth out hot pixels, attenuating noise issues
	indopttip1,indopttilt1=np.where(medttoptarr1==np.max(medttoptarr1))
	applytiptilt(tipamparr[indopttip1][0],tiltamparr[indopttilt1][0])

	optics.set_expt(expt_init)
	np.save(joindata(os.path.join("bestflats", "bestflat_{0}_{1}.npy".format(optics.name, optics.dmdims[0]))))
	print("Saved best flat")

def align_fast2(view=True):
	expt_init = optics.get_expt()
	optics.set_expt(1e-4)

	bestflat = optics.getdmc()

	#apply tip/tilt starting only from the bestflat point (start here if realigning the non-coronagraphic PSF) 
	def applytiptilt(amptip,amptilt,bestflat=bestflat): #amp is the P2V in DM units
		dmctip=amptip*tip
		dmctilt=amptilt*tilt
		dmctiptilt=remove_piston(dmctip)+remove_piston(dmctilt)+remove_piston(bestflat)+0.5 #combining tip, tilt, and best flat, setting mean piston to 0.5
		#applydmc(aperture*dmctiptilt)
		optics.applydmc(dmctiptilt)

	#make MTF side lobe mask
	xsidemaskcen,ysidemaskcen=240.7,161.0 #x and y location of the side lobe mask in the cropped image
	sidemaskrad=26.8 #radius of the side lobe mask
	mtfgrid=np.mgrid[0:optics.imdims[0],0:optics.imdims[1]]
	sidemaskrho=np.sqrt((mtfgrid[0]-ysidemaskcen)**2+(mtfgrid[1]-xsidemaskcen)**2)
	sidemask=np.zeros(optics.imdims)
	sidemaskind=np.where(sidemaskrho<sidemaskrad)
	sidemask[sidemaskind]=1

	#side lobe mask where there is no signal to measure SNR
	xnoise,ynoise=161.66,252.22
	sidemaskrhon=np.sqrt((mtfgrid[0]-ynoise)**2+(mtfgrid[1]-xnoise)**2)
	sidemaskn=np.zeros(optics.imdims)
	sidemaskindn=np.where(sidemaskrhon<sidemaskrad)
	sidemaskn[sidemaskindn]=1

	def processimabs(imin,mask): #process SCC image, isolating the sidelobe in the FFT and IFFT back to the image
		otf=np.fft.fftshift(np.fft.fft2(imin,norm='ortho')) #(1) FFT the image
		otf_masked=otf*mask #(2) multiply by binary mask to isolate side lobe or noise mask
		Iminus=np.fft.ifft2(otf_masked,norm='ortho') #(3) IFFT back to the image plane, now generating a complex-valued image
		return np.abs(Iminus)

	#tsleep=0.005 #on really good days
	tsleep=0.01 # optimized from tt_opt.optt
	#tsleep=0.4 #on bad days


	cenmaskrho=np.sqrt((mtfgrid[0]-mtfgrid[0].shape[0]/2)**2+(mtfgrid[1]-mtfgrid[0].shape[0]/2)**2) #radial grid for central MTF lobe
	cenmask = np.zeros(optics.imdims)
	cenmaskradmax,cenmaskradmin=49,10 #mask radii for central lobe, ignoring central part where the pinhole PSF is (if not ignored, this would bias the alignment algorithm)   
	cenmaskind=np.where(np.logical_and(cenmaskrho<cenmaskradmax,cenmaskrho>cenmaskradmin))
	cenmask[cenmaskind]=1

	#grid tip/tilt search 
	namp=10
	amparr=np.linspace(-0.1,0.1,namp) #note the range of this grid search is can be small, assuming day to day drifts are minimal and so you don't need to search far from the previous day to find the new optimal alignment; for larger offsets the range may need to be increases (manimum search range is -1 to 1); but, without spanning the full -1 to 1 range this requires manual tuning of the limits to ensure that the minimum is not at the edge
	ttoptarr=np.zeros((namp,namp))
	for i in range(namp):
		for j in range(namp):
			applytiptilt(amparr[i],amparr[j])
			time.sleep(tsleep)
			imopt = optics.stack(10)
			mtfopt=mtf(imopt)
			sidefraction=np.sum(mtfopt[sidemaskind])/np.sum(mtfopt)
			cenfraction=np.sum(mtfopt[cenmaskind])/np.sum(mtfopt)
			ttoptarr[i,j]=sidefraction+0.1/cenfraction #the factor of 0.01 is a relative weight; because we only expect the fringe visibility to max out at 1%, this attempts to give equal weight to both terms 

	medttoptarr = median_filter(ttoptarr,3) #smooth out hot pizels, attenuating noise issues
	indopttip,indopttilt = np.where(medttoptarr == np.max(medttoptarr))
	indopttip,indopttilt = indopttip[0],indopttilt[0]
	applytiptilt(amparr[indopttip],amparr[indopttilt])

	if view:
		plt.imshow(medttoptarr)
		plt.show()

	optics.set_expt(expt_init)

	bestflat = optics.getdmc()
	np.save(joindata(os.path.join("bestflats", "bestflat_{0}_{1}.npy".format(optics.name, optics.dmdims[0]))))
	print("Saved best flat")
