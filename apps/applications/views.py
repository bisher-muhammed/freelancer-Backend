from rest_framework import generics,permissions,status
from rest_framework.response import Response
from apps. users.models import Project
from.models import Proposal
from.serializers import ProjectDetailSerializer,ProposalCreateSerializer,MyProposalSerializer


class ProjectDetailView(generics.RetrieveAPIView):
    ''''
    Retrive details of a single project including skills and client info.
    Also returns whether the current freelancer already applied
    '''

    queryset = Project.objects.all()
    serializer_class = ProjectDetailSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = 'id'



class ProposalCreateView(generics.CreateAPIView):
    '''
    Allow a freelancer to applay to a project with bid cover letter
    '''

    serializer_class = ProposalCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"detail": "Application submitted successfully."},
            status=status.HTTP_201_CREATED
        )
    

class MyProposals(generics.ListAPIView):
    serializer_class = MyProposalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Proposal.objects
            .select_related('project', 'project__client')
            .prefetch_related('project__skills_required')
            .filter(freelancer=self.request.user)
            .order_by('-created_at')
        )


