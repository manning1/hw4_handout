import logging, numpy, openravepy

class GraspPlanner(object):

    def __init__(self, robot, base_planner, arm_planner):
        self.robot = robot
        self.base_planner = base_planner
        self.arm_planner = arm_planner

            
    def GetBasePoseForObjectGrasp(self, obj):

        # Load grasp database
        gmodel = openravepy.databases.grasping.GraspingModel(self.robot, obj)
        if not gmodel.load():
            gmodel.autogenerate()

        base_pose = None
        grasp_config = None
       
        ###################################################################
        # TODO: Here you will fill in the function to compute
        #  a base pose and associated grasp config for the 
        #  grasping the bottle
        ###################################################################
        self.graspindices = self.gmodel.graspindices
        self.grasps = self.gmodel.grasps
        grasp_config = self.order_grasps_noisy()
        grasp_config = gmodel.getGlobalGraspTransform(grasp_config, collisionfree=True)
        

        return base_pose, grasp_config

    def PlanToGrasp(self, obj):

        # Next select a pose for the base and an associated ik for the arm
        base_pose, grasp_config = self.GetBasePoseForObjectGrasp(obj)

        if base_pose is None or grasp_config is None:
            print 'Failed to find solution'
            exit()

        # Now plan to the base pose
        start_pose = numpy.array(self.base_planner.planning_env.herb.GetCurrentConfiguration())
        base_plan = self.base_planner.Plan(start_pose, base_pose)
        base_traj = self.base_planner.planning_env.herb.ConvertPlanToTrajectory(base_plan)

        print 'Executing base trajectory'
        self.base_planner.planning_env.herb.ExecuteTrajectory(base_traj)

        # Now plan the arm to the grasp configuration
        start_config = numpy.array(self.arm_planner.planning_env.herb.GetCurrentConfiguration())
        arm_plan = self.arm_planner.Plan(start_config, grasp_config)
        arm_traj = self.arm_planner.planning_env.herb.ConvertPlanToTrajectory(arm_plan)

        print 'Executing arm trajectory'
        self.arm_planner.planning_env.herb.ExecuteTrajectory(arm_traj)

        # Grasp the bottle
        task_manipulation = openravepy.interfaces.TaskManipulation(self.robot)
        task_manipultion.CloseFingers()
    


    ############################################################################
    
    def order_grasps_noisy(self):
        # order the grasps - but instead of evaluating the grasp, evaluate random perturbations of the grasp
        self.grasps_ordered_noisy = self.grasps.copy() 
        
        # Set the score with your evaluation function (over random samples) and sort
        for i,grasp in enumerate(self.grasps_ordered_noisy):
            print("evalauting grasp " + str(i))
            orig_score = self.eval_grasp(grasp)
            trials = [orig_score]
            for i in range(5):
                noisy_grasp = self.sample_random_grasp(grasp)
                trials.append(self.eval_grasp(noisy_grasp)) # add noise

            trials = np.array(trials)
            noise_score = np.mean(trials)
            grasp[self.graspindices.get('performance')] = noise_score # assign combined score

        # sort!
        order = np.argsort(self.grasps_ordered_noisy[:,self.graspindices.get('performance')[0]]) # why [0] here?
        order = order[::-1] # reverse to descending order
        self.grasps_ordered_noisy = self.grasps_ordered_noisy[order]

        # for grasp in self.grasps_ordered_noisy:
        #     print(grasp[self.graspindices.get('performance')])
        #     self.show_grasp(grasp)
        
        ind = 1
        return self.grasps_ordered_noisy[ind]; 
        


    def eval_grasp(self, grasp):
        """
        function to evaluate grasps
        returns a score, which is some metric of the grasp
        higher score should be a better grasp
        """
        with self.robot:
            #contacts is a 2d array, where contacts[i,0-2] are the positions of contact i and contacts[i,3-5] is the direction
            try:
                contacts,finalconfig,mindist,volume = self.gmodel.testGrasp(grasp=grasp,translate=True,forceclosure=False)

                obj_position = self.gmodel.target.GetTransform()[0:3,3]
                # for each contact
                G = np.zeros((6,len(contacts))) #the wrench matrix
                for i, c in enumerate(contacts):
                    pos = c[0:3] - obj_position
                    dir = -c[3:] #this is already a unit vector

                    G[0:3,i] = pos
                    G[3:6,i] = np.cross(pos,dir)

                rankG = np.linalg.matrix_rank(G)
                if (rankG<6):
                    return 0.0

                METRIC = 3

                if (METRIC==1):
                    # Metric 1: minimum singular value
                    U, s, V = np.linalg.svd(G, full_matrices=True)
                    # S = np.diag(s)
                    score = s[-1] # sigma_min
                elif (METRIC==2):
                    # Metric 2: Isotropy
                    U, s, V = np.linalg.svd(G, full_matrices=True)
                    score = s[-1]/s[0]
                else (METRIC==3):
                    # Metric 3: Volume of grasp map
                    score =  np.sqrt(np.linalg.det(np.dot(G,np.transpose(G))))
                    if (math.isnan(score)):
                        print("We'll set this value to zero.")
                        score = 0.00

                return score
            except openravepy.planning_error,e:
                #you get here if there is a failure in planning
                return  0.00


    def sample_random_grasp(self, grasp_in):
        """
        given grasp_in, create a new grasp which is altered randomly
        you can see the current position and direction of the grasp by:
        # grasp[self.graspindices.get('igrasppos')]
        # grasp[self.graspindices.get('igraspdir')]
        """
        grasp = grasp_in.copy()

        # contacts,finalconfig,mindist,volume = self.gmodel.testGrasp(grasp=grasp,translate=True,forceclosure=False)

        #sample random position
        RAND_DIST_SIGMA = 0.005  #TODO you may want to change this
        pos_orig = grasp[self.graspindices['igrasppos']]    #3x1
        #set a random position
        new_pos = pos_orig + np.random.normal(0, RAND_DIST_SIGMA,3)

        #sample random orientation
        RAND_ANGLE_SIGMA = np.pi/36 #TODO you may want to change this
        dir_orig = grasp[self.graspindices['igraspdir']]    #3x1
        roll_orig = grasp[self.graspindices['igrasproll']]  #1x1
        #set the direction and roll to be random
        new_dir = dir_orig + np.random.normal(0, RAND_ANGLE_SIGMA,3)
        new_roll = roll_orig + np.random.normal(0,RAND_ANGLE_SIGMA,1)

        grasp[self.graspindices['igrasppos']] = new_pos
        grasp[self.graspindices['igraspdir']] = new_dir
        grasp[self.graspindices['igrasproll']] = new_roll

    return grasp


    def show_grasp(self, grasp, delay=30):
        "displays the grasp"
        with openravepy.RobotStateSaver(self.gmodel.robot):
            with self.gmodel.GripperVisibility(self.gmodel.manip):
                time.sleep(0.1) # let viewer update?
                try:
                    with self.env:
                        contacts,finalconfig,mindist,volume = self.gmodel.testGrasp(grasp=grasp,translate=True,forceclosure=True)
                        #if mindist == 0:
                        #  print 'grasp is not in force closure!'
                        contactgraph = self.gmodel.drawContacts(contacts) if len(contacts) > 0 else None
                        self.gmodel.robot.GetController().Reset(0)
                        self.gmodel.robot.SetDOFValues(finalconfig[0])
                        self.gmodel.robot.SetTransform(finalconfig[1])
                        self.env.UpdatePublishedBodies()
                        time.sleep(delay)
                except openravepy.planning_error,e:
                    print 'bad grasp!',e